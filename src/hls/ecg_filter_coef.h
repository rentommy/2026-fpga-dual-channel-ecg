// ecg_filter_coef.h  —— 由 sim/gen_vectors.py 自动生成，不要手改
//
// 心电预处理滤波链的定点系数，采样率 500 Hz
//
// 链路：直流阻断(温和高通 k_g=8 + 矩形窗 L=320 + 延迟补偿 D) → 50Hz 陷波(Q=15) → 31 抽头 FIR 低通(40Hz)
//
// 每通道每采样点的乘法**次数**：1 + 5 + 16 = 22
// 注意这是次数不是乘法器个数：500 SPS 下每个采样周期有 200,000 个 100MHz 时钟，
// 8 通道共 176 次乘法，一个 DSP48 时分复用即可（占用率 0.088%）。
// 双通路（诊断+低延迟）：矩形窗归一化共享，每通道 1+2*21=43 次，
// 8 通道共 344 次，占 0.172%。
// 架构依据见 report/design_phase1.md 第 2.0 节。
//
// 系数一律 18 位有符号 —— DSP48E1 是 25x18 乘法器，18 位是系数端口的
// 原生宽度，比 16 位精度高 4 倍而不多占资源。

#ifndef ECG_FILTER_COEF_H
#define ECG_FILTER_COEF_H

//采样率
#define ECG_FS          500
//系数存储位宽
#define COEF_BITS       18
//==========================================================================================================
// ── ① 直流阻断：温和高通 + 矩形窗基线估计 + 延迟补偿 ──
//   acc  += (x - acc) >> DC_SHIFT;                 // 温和高通，0 乘法
//   yg    = x - acc;
//   sum  += yg - yg_hist[n - DC_BOX_L];            // 滑动求和，0 乘法
//   lp    = (sum * DC_BOX_SCALE) >> DC_BOX_FRAC;   // 归一化 1/L，1 次乘法
//   y     = yg_delay[n - D] - lp;                  // D 每通道独立
//
// 为什么要延迟补偿：
//   一阶 IIR 估基线时，群延迟随频率变 11 倍（0.05~1 Hz 内 22~249 点），
//   一个固定的 D 只能对齐一个频率，残余相位把 T 波削掉一半。
//   矩形窗的群延迟恒为 (L-1)/2，所有频率一次对齐。
//   实测逐拍 ST60 误差 0.152 -> 0.082 mV，T 峰误差 0.270 -> 0.132 mV。
//
// 为什么 L 取 320（640 ms）：
//   L 必须接近一个心拍（实测 RR 824/878 ms = 412/439 点）。窗比一拍短时，
//   窗里装着 QRS 和 T 波本身，基线被顶高，ST 系统性读低：
//   L=256(512ms) 实测偏差 -0.068 mV，L=320 降到 -0.028 mV。
//
// D 每通道独立配置 —— 这是多通道扩展的关键：
//   DC_DELAY_ECG  = (L-1)/2 = 159，低频对齐最准
//                   总延迟 (D+FIR_DELAY)/FS = 348 ms
//                   诊断通路：ST 段测量、波形存档、模型推理
//   DC_DELAY_FAST = 0，不补相位，总延迟 30 ms
//                   低延迟通路：实时显示、报警，以及肌电一类闭环场景
//                   （肌电控制文献要求 100~125 ms 以内，348 ms 不适用）
//
//   两条通路共享温和高通和矩形窗，只有延迟线/陷波/FIR 各一份。
//   低延迟通路的延迟**不因为旁边多了诊断通路而增加一个时钟** —— 空间并行，
//   这是 FPGA 相对 CPU 的本质差别，见 report/why_fpga.md。

//温和高通移位位数，fc = FS/(2*pi*2^DC_SHIFT) = 0.311 Hz
#define DC_SHIFT        8
//矩形窗长度（点）
#define DC_BOX_L        320
//矩形窗归一化：lp = (sum * DC_BOX_SCALE) >> DC_BOX_FRAC
//直流增益 = DC_BOX_SCALE * DC_BOX_L / 2^DC_BOX_FRAC = 1.000061
#define DC_BOX_FRAC     20
#define DC_BOX_SCALE    3277
//滑动和位宽：DATA_BITS + ceil(log2(DC_BOX_L)) = 33 位，留 1 位余量
#define DC_BOX_ACC_BITS 34
//延迟线深度上限（按最大的 D 开 RAM）
#define DC_DELAY_MAX    192
//诊断通路延迟（点）
#define DC_DELAY_ECG    159
//低延迟通路延迟（点）
#define DC_DELAY_FAST   0
//通道数 / 每通道并行通路数
#define N_CHANNELS      8
#define N_PATHS         2
//每通道每通路的延迟配置，上板可改成 AXI-Lite 寄存器
static const int DC_DELAY_CFG[N_CHANNELS][N_PATHS] = {
    { DC_DELAY_ECG,  DC_DELAY_FAST },   // ch0  心电 导联I
    { DC_DELAY_ECG,  DC_DELAY_FAST },   // ch1  心电 导联II
    { DC_DELAY_FAST, DC_DELAY_FAST },   // ch2  扩展位：肌电等闭环场景，两路都走低延迟
    { DC_DELAY_FAST, DC_DELAY_FAST },   // ch3
    { DC_DELAY_ECG,  DC_DELAY_FAST },   // ch4  扩展位：按需逐通道改
    { DC_DELAY_ECG,  DC_DELAY_FAST },   // ch5
    { DC_DELAY_ECG,  DC_DELAY_FAST },   // ch6
    { DC_DELAY_ECG,  DC_DELAY_FAST }    // ch7
};
//==========================================================================================================
// ── ② 50Hz 陷波 biquad，直接 I 型，系数 Q2.16 ──
//   acc  = B0*x[n] + B1*x[n-1] + B2*x[n-2] - A1*y[n-1] - A2*y[n-2];
//   y[n] = acc >> NOTCH_FRAC;
// 极点半径 0.97927。注入 224uV 工频实测衰减 -61.9 dB

//小数点位置(需要的位移量)
#define NOTCH_FRAC      16
//位移后的1
#define NOTCH_ONE       65536
//陷波器系数
#define NOTCH_B0        64191
#define NOTCH_B1        -103864
#define NOTCH_B2        64191
#define NOTCH_A1        -103864
#define NOTCH_A2        62847
//==========================================================================================================
// ── ③ FIR 低通，系数对称，可折叠成 16 个乘法器，系数 Q1.19 ──
//   折叠写法：h[i] * (x[n-i] + x[n-(FIR_TAPS-1-i)])，一个乘法算两项

//FIR 抽头数
#define FIR_TAPS        31
//小数点位置(需要的位移量)
#define FIR_FRAC        19
//位移后的1
#define FIR_ONE         524288
// 群延迟 = 30 ms，算 RR 间期时被减掉
#define FIR_DELAY       15
//响应系数数组
static const int FIR_COEF[FIR_TAPS] = {
        844,     732,     381,    -579,   -2403,   -4903,   -7222,   -7880,
      -5143,    2370,   15054,   31895,   50467,   67418,   79315,   83597,
      79315,   67418,   50467,   31895,   15054,    2370,   -5143,   -7880,
      -7222,   -4903,   -2403,    -579,     381,     732,     844
};

// ── 数据通路位宽（依据 sim/characterize_notch.py 第 5 节实测峰值）──
//   输入      24 位有符号（ADS1292 原生输出）
//   各级中间  24 位有符号足够，实测各级峰值不到 19 位
//   FIR 累加器 24 + 18 + ceil(log2(31)) = 47 位 → 取 48 位（DSP48 原生累加宽度）

//ads1292输出位宽
#define DATA_BITS       24
//累加器位宽
#define ACC_BITS        48

#endif // ECG_FILTER_COEF_H

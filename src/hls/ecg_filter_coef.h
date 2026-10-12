// ecg_filter_coef.h  —— 由 sim/gen_vectors.py 自动生成，不要手改
//
// 心电预处理滤波链的定点系数，采样率 500 Hz
//
// 链路：直流阻断(移位 k=7 × 2 级) → 50Hz 陷波(Q=15) → 31 抽头 FIR 低通(40Hz)
//
// 每通道每采样点的乘法**次数**：0 + 5 + 16 = 21
// 注意这是次数不是乘法器个数：500 SPS 下每个采样周期有 200,000 个 100MHz 时钟，
// 8 通道共 168 次乘法，一个 DSP48 时分复用即可（占用率 0.08%）。
// 架构依据见 report/design_phase1.md 第 2.0 节。
//
// 系数一律 18 位有符号 —— DSP48E1 是 25x18 乘法器，18 位是系数端口的
// 原生宽度，比 16 位精度高 4 倍而不多占资源。

#ifndef ECG_FILTER_COEF_H
#define ECG_FILTER_COEF_H

#define ECG_FS          500
#define COEF_BITS       18

// ── ① 直流阻断（零乘法器）──
//   for (s = 0; s < DC_STAGES; s++) {
//       acc[s] += (x - acc[s]) >> DC_SHIFT;
//       x       = x - acc[s];
//   }
// 单级是一阶高通，fc = FS / (2*pi*2^DC_SHIFT) = 0.622 Hz
// 级联 2 级得到 2 阶，注入 2mV/0.2Hz 呼吸漂移实测残留 0.17mV
#define DC_SHIFT        7
#define DC_STAGES       2

// ── ② 50Hz 陷波 biquad，直接 I 型，系数 Q2.16 ──
//   acc  = B0*x[n] + B1*x[n-1] + B2*x[n-2] - A1*y[n-1] - A2*y[n-2];
//   y[n] = acc >> NOTCH_FRAC;
// 极点半径 0.97927。注入 224uV 工频实测衰减 -61.9 dB
#define NOTCH_FRAC      16
#define NOTCH_ONE       65536
#define NOTCH_B0        64191
#define NOTCH_B1        -103864
#define NOTCH_B2        64191
#define NOTCH_A1        -103864
#define NOTCH_A2        62847

// ── ③ FIR 低通，系数对称，可折叠成 16 个乘法器，系数 Q1.19 ──
//   折叠写法：h[i] * (x[n-i] + x[n-(FIR_TAPS-1-i)])，一个乘法算两项
#define FIR_TAPS        31
#define FIR_FRAC        19
#define FIR_ONE         524288
#define FIR_DELAY       15      // 群延迟 = 30 ms，算 RR 间期时被减掉

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
#define DATA_BITS       24
#define ACC_BITS        48

#endif // ECG_FILTER_COEF_H

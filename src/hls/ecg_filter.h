// ecg_filter.h —— DUT 接口契约
//
// 这个文件定义"硬件长什么样"，是 HLS 实现、测试平台、PS 侧驱动三方的共同依据。
// 系数和算法参数在 ecg_filter_coef.h（由 sim/gen_vectors.py 生成，不要手改）；
// 这里只放**实现侧**的决定：位宽、状态结构、函数签名、时序约定。
//
// 设计要点：
//   - 每通道并行 N_PATHS 条通路，各自的延迟 D 由 DC_DELAY_CFG 配置
//     （诊断通路 D=159 → 348 ms；低延迟通路 D=0 → 30 ms）
//   - 矩形窗历史 box_hist[] **兼作各通路的延迟线** ——
//     它已经存着最近 DC_BOX_L=320 个 yg，而 DC_DELAY_MAX=192 < 320，
//     延迟抽头直接从这块 RAM 上多开一个读口即可，不另开延迟线
//   - 核心是"一个采样点进、N_PATHS 个采样点出"的纯函数，
//     不含 hls::stream，用 g++ 就能跑 C 仿真

#ifndef ECG_FILTER_H
#define ECG_FILTER_H

#include <stdint.h>
#include "ecg_filter_coef.h"

// ── 实现侧位宽 ──
// 温和高通 acc += (x-acc)>>DC_SHIFT 若用整数存会有死区：
// |x-acc| < 2^DC_SHIFT 时增量截断成 0，累加器卡住，死区 ±256 码 = ±0.0123 mV。
// 给 acc 多留 DC_ACC_FRAC 位小数后死区降到 ±1/256 码，可忽略。
#define DC_ACC_FRAC     8
#define DC_ACC_BITS     (DATA_BITS + DC_ACC_FRAC + 2)   // 34

// 预热期输出无效，上板丢弃前 ECG_WARMUP 点 = 543 点 ≈ 1.09 秒（500 SPS）。
// 三项依次是：矩形窗填满 DC_BOX_L、延迟线灌满 DC_DELAY_MAX、FIR 吃满 FIR_TAPS。
// 取三者之和而不只是 DC_BOX_L —— 保守，确保热身区一定覆盖全部状态的建立。
#define ECG_WARMUP      (DC_BOX_L + DC_DELAY_MAX + FIR_TAPS)   // 543

// 综合时用精确位宽的 ap_int，省 BRAM（24 位 vs 32 位，省 25%）；
// C 仿真时用原生整型，g++ 不需要 Vitis 头文件。
// 两边数值行为一致的前提是各级中间量都装得下 —— 由测试平台第 ④ 项核对，
// 实测峰值占 17.8 / 24 位，余量 6.2 位。
#ifdef __VITIS_HLS__
#include <ap_int.h>
typedef ap_int<DATA_BITS>       ecg_sample_t;   // 样本
typedef ap_int<ACC_BITS>        ecg_acc_t;      // 陷波 / FIR 累加器
typedef ap_int<DC_ACC_BITS>     ecg_hpacc_t;    // 温和高通累加器
typedef ap_int<DC_BOX_ACC_BITS> ecg_boxacc_t;   // 矩形窗滑动和
#else
typedef int32_t ecg_sample_t;
typedef int64_t ecg_acc_t;
typedef int64_t ecg_hpacc_t;
typedef int64_t ecg_boxacc_t;
#endif

// ── 单通道状态 ──
// 综合时整个结构体落到 BRAM，8 通道时分复用同一套算术单元
typedef struct {
    ecg_hpacc_t  hp_acc;                      // 温和高通累加器，Q<DC_ACC_FRAC>
    ecg_sample_t box_hist[DC_BOX_L];          // yg 历史，兼作延迟线
    ecg_boxacc_t box_sum;                     // 滑动和
    int32_t      box_ptr;                     // 环形指针，指向将被挤出窗口的那个

    ecg_sample_t notch_x1[N_PATHS], notch_x2[N_PATHS];   // 陷波输入历史
    ecg_sample_t notch_y1[N_PATHS], notch_y2[N_PATHS];   // 陷波输出历史（移位后）
    ecg_sample_t fir_hist[N_PATHS][FIR_TAPS];            // FIR 历史
    int32_t      fir_ptr[N_PATHS];

    int32_t      delay[N_PATHS];              // 本通道各通路的 D，可运行时改
} ecg_chan_state_t;

// ── 运行期统计：测试平台用它核对位宽声明 ──
// 契约里声称"各级中间 24 位够用、累加器 48 位够用"，这个结构体把实测峰值
// 带出来，测试平台据此判定声明是否成立（而不是靠人眼看波形）
typedef struct {
    ecg_acc_t max_abs_yg;        // 温和高通输出
    ecg_acc_t max_abs_boxsum;    // 滑动和
    ecg_acc_t max_abs_dcout;     // 直流阻断输出
    ecg_acc_t max_abs_notchacc;  // 陷波累加器（移位前）
    ecg_acc_t max_abs_firacc;    // FIR 累加器（移位前）
    ecg_acc_t max_abs_out;       // 最终输出
} ecg_range_t;

// ── 接口 ──

// 复位单通道状态；delay_cfg 取 DC_DELAY_CFG[ch]，传 NULL 则用 {DC_DELAY_ECG, DC_DELAY_FAST}
void ecg_filter_init(ecg_chan_state_t *st, const int *delay_cfg);

void ecg_range_init(ecg_range_t *r);

// 单采样点处理：x 进，y[0..N_PATHS-1] 出
//   y[p] 对应输入 x[n - (st->delay[p] + FIR_DELAY)]
//   rng 传 NULL 则不统计
void ecg_filter_sample(ecg_chan_state_t *st, ecg_sample_t x,
                       ecg_sample_t y[N_PATHS], ecg_range_t *rng);

// HLS 顶层：一块数据、多通道
//   in  [n*N_CHANNELS + ch]              —— 交织存放
//   out [(n*N_CHANNELS + ch)*N_PATHS + p]
//   综合时在这一层加 PIPELINE / ALLOCATION 约束，把 8 通道压到一套算术单元上
void ecg_filter_block(const ecg_sample_t *in, ecg_sample_t *out, int32_t n_samples,
                      ecg_chan_state_t state[N_CHANNELS]);

#endif // ECG_FILTER_H

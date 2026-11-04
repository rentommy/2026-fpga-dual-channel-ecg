// ecg_filter.cpp —— DUT 定点实现
//
// 和 src/ps/hw_filter_ref.py 的 chain_hw_v2 对应，差别只在算术：
// 这里全程整数，参考实现是双精度浮点。两者之差就是"算术量化误差"，
// 由 tb_ecg_filter.cpp 量化并设阈值。
//
// 移位约定：
//   右移一律是**算术**右移（高位补符号位）。心电是有符号量且均值为负，
//   逻辑右移会把负数变成巨大的正数。C++20 起对有符号数已明确规定为算术移位，
//   更早的标准是实现定义 —— gcc/clang/MSVC 实际都是算术移位，
//   测试平台开头有一处运行时断言兜底。
//   综合时换成 ap_int<N>，其 >> 本身就是算术移位。

#include "ecg_filter.h"

// 带四舍五入的算术右移：比截断少一半偏差，硬件上只多一个加法
#define SHR_RND(v, s)  ((((ecg_acc_t)(v)) + ((ecg_acc_t)1 << ((s) - 1))) >> (s))


void ecg_filter_init(ecg_chan_state_t *st, const int *delay_cfg)
{
    st->hp_acc = 0;
    st->box_sum = 0;
    st->box_ptr = 0;
    for (int i = 0; i < DC_BOX_L; i++)
        st->box_hist[i] = 0;
    for (int p = 0; p < N_PATHS; p++) {
        st->notch_x1[p] = st->notch_x2[p] = 0;
        st->notch_y1[p] = st->notch_y2[p] = 0;
        st->fir_ptr[p] = 0;
        for (int i = 0; i < FIR_TAPS; i++)
            st->fir_hist[p][i] = 0;
    }
    if (delay_cfg) {
        for (int p = 0; p < N_PATHS; p++)
            st->delay[p] = delay_cfg[p];
    } else {
        st->delay[0] = DC_DELAY_ECG;
        st->delay[1] = DC_DELAY_FAST;
    }
}


void ecg_range_init(ecg_range_t *r)
{
    r->max_abs_yg = r->max_abs_boxsum = r->max_abs_dcout = 0;
    r->max_abs_notchacc = r->max_abs_firacc = r->max_abs_out = 0;
}


static inline void track(ecg_acc_t *slot, ecg_acc_t v)
{
    ecg_acc_t a = (v < 0) ? (ecg_acc_t)(-v) : v;
    if (a > *slot) *slot = a;
}


void ecg_filter_sample(ecg_chan_state_t *st, ecg_sample_t x,
                       ecg_sample_t y[N_PATHS], ecg_range_t *rng)
{
    // ── ① 温和高通（0 乘法）──
    // acc 多带 DC_ACC_FRAC 位小数，否则 |x-acc| < 2^DC_SHIFT 时增量截断成 0，
    // 累加器卡死区里不动
    ecg_hpacc_t xq = ((ecg_hpacc_t)x) << DC_ACC_FRAC;
    st->hp_acc += (xq - st->hp_acc) >> DC_SHIFT;
    ecg_sample_t yg = x - (ecg_sample_t)(st->hp_acc >> DC_ACC_FRAC);

    // ── ② 矩形窗基线估计（滑动求和，0 乘法）──
    // box_hist[box_ptr] 此刻存的是即将被挤出窗口的那个样本
    st->box_sum += (ecg_boxacc_t)yg - (ecg_boxacc_t)st->box_hist[st->box_ptr];
    st->box_hist[st->box_ptr] = yg;
    st->box_ptr = (st->box_ptr + 1 == DC_BOX_L) ? 0 : (st->box_ptr + 1);

    // 归一化 1/L：320 不是 2 的幂，用一次常数乘法代替除法
    ecg_sample_t lp = (ecg_sample_t)SHR_RND((ecg_acc_t)st->box_sum * DC_BOX_SCALE, DC_BOX_FRAC);

    if (rng) {
        track(&rng->max_abs_yg, yg);
        track(&rng->max_abs_boxsum, st->box_sum);
    }

    for (int p = 0; p < N_PATHS; p++) {
        // ── ③ 延迟抽头 + 相减 ──
        // yg[n] 在 box_hist[(box_ptr-1+L) % L]，往回数 D 个就是 yg[n-D]。
        // DC_DELAY_MAX < DC_BOX_L，所以延迟线不用单独开 RAM，
        // 在矩形窗历史上多开一个读口即可
        int32_t idx = st->box_ptr + DC_BOX_L - 1 - st->delay[p];
        if (idx >= DC_BOX_L) idx -= DC_BOX_L;
        ecg_sample_t dc = st->box_hist[idx] - lp;

        // ── ④ 50Hz 陷波 biquad，直接 I 型 ──
        ecg_acc_t na = (ecg_acc_t)NOTCH_B0 * dc
                     + (ecg_acc_t)NOTCH_B1 * st->notch_x1[p]
                     + (ecg_acc_t)NOTCH_B2 * st->notch_x2[p]
                     - (ecg_acc_t)NOTCH_A1 * st->notch_y1[p]
                     - (ecg_acc_t)NOTCH_A2 * st->notch_y2[p];
        ecg_sample_t nout = (ecg_sample_t)SHR_RND(na, NOTCH_FRAC);

        st->notch_x2[p] = st->notch_x1[p];  st->notch_x1[p] = dc;
        st->notch_y2[p] = st->notch_y1[p];  st->notch_y1[p] = nout;

        // ── ⑤ FIR 低通，系数对称折叠成 16 次乘法 ──
        st->fir_hist[p][st->fir_ptr[p]] = nout;
        ecg_acc_t fa = 0;
        for (int i = 0; i < FIR_TAPS / 2; i++) {
            int32_t ia = st->fir_ptr[p] - i;               if (ia < 0) ia += FIR_TAPS;
            int32_t ib = st->fir_ptr[p] - (FIR_TAPS - 1 - i);
            if (ib < 0) ib += FIR_TAPS;
            fa += (ecg_acc_t)FIR_COEF[i]
                * ((ecg_acc_t)st->fir_hist[p][ia] + (ecg_acc_t)st->fir_hist[p][ib]);
        }
        int32_t ic = st->fir_ptr[p] - FIR_TAPS / 2;        if (ic < 0) ic += FIR_TAPS;
        fa += (ecg_acc_t)FIR_COEF[FIR_TAPS / 2] * (ecg_acc_t)st->fir_hist[p][ic];

        st->fir_ptr[p] = (st->fir_ptr[p] + 1 == FIR_TAPS) ? 0 : (st->fir_ptr[p] + 1);

        y[p] = (ecg_sample_t)SHR_RND(fa, FIR_FRAC);

        if (rng) {
            track(&rng->max_abs_dcout, dc);
            track(&rng->max_abs_notchacc, na);
            track(&rng->max_abs_firacc, fa);
            track(&rng->max_abs_out, y[p]);
        }
    }
}


void ecg_filter_block(const ecg_sample_t *in, ecg_sample_t *out, int32_t n_samples,
                      ecg_chan_state_t state[N_CHANNELS])
{
    // 综合时在这里加约束：
    //   #pragma HLS ALLOCATION operation instances=mul limit=1
    //   #pragma HLS PIPELINE II=1   （放在 ch 循环上）
    //   #pragma HLS ARRAY_PARTITION variable=state complete dim=1
    // 500 SPS 下每采样周期 200,000 个时钟，8 通道 x 2 通路 x 22 次乘法 = 352 次，
    // 一个 DSP48 时分复用绰绰有余（0.176%）
    for (int32_t n = 0; n < n_samples; n++) {
        for (int ch = 0; ch < N_CHANNELS; ch++) {
            ecg_sample_t y[N_PATHS];
            ecg_filter_sample(&state[ch], in[n * N_CHANNELS + ch], y, 0);
            for (int p = 0; p < N_PATHS; p++)
                out[(n * N_CHANNELS + ch) * N_PATHS + p] = y[p];
        }
    }
}

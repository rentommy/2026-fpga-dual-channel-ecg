// ecg_filter_top.cpp —— Vitis HLS 综合顶层
//
// 把 ecg_filter.cpp 里的纯 C 核心包一层 AXI 接口和综合约束。
// 核心本身不含任何 HLS 专有写法，用 g++ 就能跑 C 仿真（见 tb_ecg_filter.cpp）；
// 综合相关的东西全部集中在本文件，便于替换接口形式（m_axi / axis / ap_fifo）。
//
// 接口选 m_axi + s_axilite 的理由：PYNQ 侧用 pynq.allocate 分配缓冲、
// 写几个寄存器就能驱动，不需要额外的 DMA IP。
// 若后续改成 PL 直接收 SPI，把 in 换成 hls::stream 即可，核心不动。
//
// 外部端口用 int32_t 而不是 ap_int<24>：AXI 要求字节对齐，24 位不是。
// 24 位只用在**片内存储**上（box_hist / fir_hist），那里才是 BRAM 的大头。

#include "ecg_filter.h"

// 一次调用最多处理多少个采样点。500 SPS 下 4096 点 = 8.2 秒。
// 只影响 m_axi 的 depth 声明（给 cosim 用），不影响综合出的逻辑。
#define ECG_MAX_BLOCK 4096

void ecg_filter_top(const int32_t *in, int32_t *out,
                    int32_t n_samples, int32_t do_reset)
{
// ── 接口 ──
#pragma HLS INTERFACE m_axi     port=in   offset=slave bundle=gmem0 \
    depth=32768
#pragma HLS INTERFACE m_axi     port=out  offset=slave bundle=gmem1 \
    depth=65536
#pragma HLS INTERFACE s_axilite port=in         bundle=ctrl
#pragma HLS INTERFACE s_axilite port=out        bundle=ctrl
#pragma HLS INTERFACE s_axilite port=n_samples  bundle=ctrl
#pragma HLS INTERFACE s_axilite port=do_reset   bundle=ctrl
#pragma HLS INTERFACE s_axilite port=return     bundle=ctrl

    // ── 状态：跨调用保持，综合成片内 BRAM ──
    // complete dim=1 让 8 个通道各自一块 RAM，互不争端口；
    // 每个结构体里的 box_hist[320] 仍是数组 → 映射到 BRAM
    static ecg_chan_state_t st[N_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=st complete dim=1

    // ── 资源约束：强制只用 1 个乘法器 ──
    // 8 通道 x 2 通路 x 21 次 + 8 次归一化 = 344 次乘法/采样点。
    // 500 SPS 下每采样周期有 200,000 个 100MHz 时钟，串行跑完绰绰有余。
    // 旧版 vivado_hls 的写法是：
    //   #pragma HLS ALLOCATION instances=mul limit=1 operation
#pragma HLS ALLOCATION operation instances=mul limit=1

    if (do_reset) {
    reset_ch:
        for (int ch = 0; ch < N_CHANNELS; ch++) {
#pragma HLS LOOP_TRIPCOUNT min=8 max=8
            ecg_filter_init(&st[ch], DC_DELAY_CFG[ch]);
        }
    }

sample_loop:
    for (int32_t n = 0; n < n_samples; n++) {
#pragma HLS LOOP_TRIPCOUNT min=500 max=4096 avg=2000
    chan_loop:
        for (int ch = 0; ch < N_CHANNELS; ch++) {
#pragma HLS LOOP_TRIPCOUNT min=8 max=8
            ecg_sample_t y[N_PATHS];
            ecg_filter_sample(&st[ch],
                              (ecg_sample_t)in[n * N_CHANNELS + ch], y, 0);
            for (int p = 0; p < N_PATHS; p++)
                out[(n * N_CHANNELS + ch) * N_PATHS + p] = (int32_t)y[p];
        }
    }
}

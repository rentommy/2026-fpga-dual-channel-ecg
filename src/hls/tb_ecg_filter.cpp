// tb_ecg_filter.cpp —— C 仿真测试平台
//
// 职责：把 DUT 的定点输出和 sim/gen_vectors.py 生成的浮点黄金参考逐点比对，
//       任何一项不达标就返回非 0 退出码（CI / Vitis C-SIM 据此判定失败）。
//
// 五项检查：
//   ① 合成测试 60 秒数据 vs 黄金参考（诊断通路）
//   ② 单位冲激响应 vs 黄金参考 —— 抓系数装反、装错、折叠写错
//   ③ 50Hz 纯音抑制 —— 抓陷波器没生效
//   ④ 各级中间量峰值 vs 契约声称的位宽 —— 抓位宽声明不成立
//   ⑤ 两条通路的延迟是否就是 DC_DELAY_CFG 说的那个值 —— 抓延迟线接错
//
// 编译（不需要 Vitis）：
//   g++ -std=c++11 -O2 -I src/hls src/hls/ecg_filter.cpp src/hls/tb_ecg_filter.cpp \
//       -o build/tb_ecg_filter && ./build/tb_ecg_filter
//
// 在 Vitis HLS 里作为 testbench 直接加入工程即可，无需改动。

#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstring>
#include <cstdarg>
#include <vector>
#include <string>
#include "ecg_filter.h"

static const double LSB_UV = 48.081e-3;          // 1 码 = 48.081e-3 µV
static const char  *DATA_DIR = "data";

static int g_fail = 0;

static void report(const char *name, bool ok, const char *fmt, ...)
{
    va_list ap; va_start(ap, fmt);
    char buf[512]; vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    printf("  [%s] %-34s %s\n", ok ? "通过" : "失败", name, buf);
    if (!ok) g_fail++;
}

static bool load_txt(const char *rel, std::vector<double> &out)
{
    std::string p = std::string(DATA_DIR) + "/" + rel;
    FILE *f = fopen(p.c_str(), "r");
    if (!f) { printf("  无法打开 %s\n", p.c_str()); return false; }
    out.clear();
    char line[128];
    while (fgets(line, sizeof line, f)) {
        char *e; double v = strtod(line, &e);
        if (e != line) out.push_back(v);
    }
    fclose(f);
    return !out.empty();
}

// 跑一遍 DUT，返回各通路输出
static void run_dut(const std::vector<double> &in,
                    std::vector<std::vector<ecg_sample_t> > &out,
                    ecg_range_t *rng)
{
    ecg_chan_state_t st;
    ecg_filter_init(&st, 0);
    ecg_range_init(rng);
    out.assign(N_PATHS, std::vector<ecg_sample_t>(in.size()));
    for (size_t n = 0; n < in.size(); n++) {
        ecg_sample_t y[N_PATHS];
        ecg_filter_sample(&st, (ecg_sample_t)llround(in[n]), y, rng);
        for (int p = 0; p < N_PATHS; p++) out[p][n] = y[p];
    }
}

// 与黄金参考比对，跳过热身段
struct Diff { double max_abs; double rms; size_t at; size_t n; };

static Diff compare(const std::vector<ecg_sample_t> &dut,
                    const std::vector<double> &gold, size_t skip)
{
    Diff d = {0, 0, 0, 0};
    double s2 = 0;
    for (size_t n = skip; n < dut.size() && n < gold.size(); n++) {
        double e = fabs((double)dut[n] - gold[n]);
        if (e > d.max_abs) { d.max_abs = e; d.at = n; }
        s2 += e * e; d.n++;
    }
    d.rms = d.n ? sqrt(s2 / d.n) : 0;
    return d;
}


// ── 判定阈值 ──
// 来源：量化误差的理论上界 + 首次合成测试留 3 倍余量，见 src/hls/INTERFACE.md §5
#define TOL_MAX_LSB     64.0      // 单点最大偏差
#define TOL_RMS_LSB     8.0       // 全段 RMS 偏差
#define TOL_50HZ_CODE   64.0      // 50Hz 纯音残留
#define TOL_DELAY_ERR   0         // 延迟必须精确相符


int main()
{
    printf("================ ECG 滤波链 C 仿真 ================\n");
    printf("定稿参数：温和高通 k=%d，矩形窗 L=%d，延迟 诊断/低延迟 = %d/%d，"
           "陷波 Q2.%d，FIR %d 抽头\n\n",
           DC_SHIFT, DC_BOX_L, DC_DELAY_ECG, DC_DELAY_FAST, NOTCH_FRAC, FIR_TAPS);

    // ── ⓪ 算术右移自检 ──
    // 心电是有符号量且均值为负，逻辑右移会把负数变成巨大正数
    {
        ecg_acc_t v = -8;
        report("算术右移", (v >> 1) == -4, "(-8)>>1 = %lld，需为 -4", (long long)(v >> 1));
        if (g_fail) { printf("\n编译器的有符号右移不是算术移位，后续结果无意义\n"); return 1; }
    }

    std::vector<double> raw, gold;
    if (!load_txt("input_raw.txt", raw) || !load_txt("golden_float.txt", gold)) {
        printf("\n读不到测试向量，先跑 python sim/gen_vectors.py\n");
        return 1;
    }

    // ── ① 合成测试数据 vs 黄金参考（诊断通路 = path 0）──
    printf("① 合成测试 %zu 点（%.1f 秒）vs 黄金参考，跳过热身 %d 点\n",
           raw.size(), raw.size() / (double)ECG_FS, ECG_WARMUP);
    std::vector<std::vector<ecg_sample_t> > out;
    ecg_range_t rng;
    run_dut(raw, out, &rng);

    Diff d = compare(out[0], gold, ECG_WARMUP);
    report("最大偏差", d.max_abs <= TOL_MAX_LSB,
           "%.1f 码 = %.4f µV（阈值 %.0f），出现在第 %zu 点",
           d.max_abs, d.max_abs * LSB_UV, TOL_MAX_LSB, d.at);
    report("RMS 偏差", d.rms <= TOL_RMS_LSB,
           "%.3f 码 = %.4f µV（阈值 %.0f），比较 %zu 点",
           d.rms, d.rms * LSB_UV, TOL_RMS_LSB, d.n);

    // ── ② 单位冲激响应 ──
    printf("\n② 单位冲激响应\n");
    std::vector<double> imp, imp_gold;
    if (load_txt("testcase_impulse.txt", imp) &&
        load_txt("testcase_impulse_golden.txt", imp_gold)) {
        std::vector<std::vector<ecg_sample_t> > io; ecg_range_t ir;
        run_dut(imp, io, &ir);
        // 向量长 1024 点，大于 ECG_WARMUP，跳过热身后仍有足够长度可比
        Diff id = compare(io[0], imp_gold, ECG_WARMUP);
        report("冲激响应一致", id.max_abs <= TOL_MAX_LSB,
               "最大偏差 %.1f 码（阈值 %.0f）", id.max_abs, TOL_MAX_LSB);
    } else {
        report("冲激向量", false, "读不到 testcase_impulse*.txt");
    }

    // ── ③ 50Hz 抑制 ──
    printf("\n③ 50Hz 工频抑制\n");
    std::vector<double> s50;
    if (load_txt("testcase_50hz.txt", s50)) {
        std::vector<std::vector<ecg_sample_t> > so; ecg_range_t sr;
        run_dut(s50, so, &sr);
        double amp_in = 0, amp_out = 0;
        for (size_t n = 0; n < s50.size(); n++)
            if (fabs(s50[n]) > amp_in) amp_in = fabs(s50[n]);
        for (size_t n = ECG_WARMUP; n < so[0].size(); n++)
            if (fabs((double)so[0][n]) > amp_out) amp_out = fabs((double)so[0][n]);
        report("50Hz 残留", amp_out <= TOL_50HZ_CODE,
               "输入 %.0f 码 → 残留 %.1f 码（%.1f dB，阈值 %.0f）",
               amp_in, amp_out, 20 * log10((amp_out + 1e-9) / amp_in), TOL_50HZ_CODE);
    } else {
        report("50Hz 向量", false, "读不到 testcase_50hz.txt");
    }

    // ── ④ 位宽声明核对 ──
    // 契约声称各级中间量 24 位够用、累加器 48 位够用。
    // 这里拿合成测试峰值去核对，而不是靠人眼看波形
    printf("\n④ 位宽声明核对（合成测试峰值 vs 契约声称）\n");
    struct { const char *name; ecg_acc_t peak; int bits; } chk[] = {
        { "温和高通输出 yg",   rng.max_abs_yg,       DATA_BITS      },
        { "矩形窗滑动和",      rng.max_abs_boxsum,   DC_BOX_ACC_BITS},
        { "直流阻断输出",      rng.max_abs_dcout,    DATA_BITS      },
        { "陷波累加器",        rng.max_abs_notchacc, ACC_BITS       },
        { "FIR 累加器",        rng.max_abs_firacc,   ACC_BITS       },
        { "最终输出",          rng.max_abs_out,      DATA_BITS      },
    };
    for (size_t i = 0; i < sizeof chk / sizeof chk[0]; i++) {
        double used = chk[i].peak > 0 ? (log((double)chk[i].peak) / log(2.0) + 1) : 1;
        bool ok = used <= chk[i].bits;
        report(chk[i].name, ok, "峰值 %lld，占 %.1f / %d 位（余量 %.1f 位）",
               (long long)chk[i].peak, used, chk[i].bits, chk[i].bits - used);
    }

    // ── ⑤ 两条通路的延迟 ──
    // 喂一个冲激，看每条通路的输出峰值落在第几点。
    // 应当正好是 DC_DELAY_CFG[p] + FIR_DELAY
    printf("\n⑤ 通路延迟核对（契约：path p 的延迟 = DC_DELAY_CFG[p] + FIR_DELAY）\n");
    {
        std::vector<double> ii(DC_BOX_L + DC_DELAY_MAX + 2 * FIR_TAPS, 0.0);
        ii[0] = (double)(1 << 20);
        std::vector<std::vector<ecg_sample_t> > io; ecg_range_t ir;
        run_dut(ii, io, &ir);
        const int want[N_PATHS] = { DC_DELAY_ECG + FIR_DELAY, DC_DELAY_FAST + FIR_DELAY };
        for (int p = 0; p < N_PATHS; p++) {
            size_t at = 0; double pk = 0;
            for (size_t n = 0; n < io[p].size(); n++)
                if (fabs((double)io[p][n]) > pk) { pk = fabs((double)io[p][n]); at = n; }
            char nm[64]; snprintf(nm, sizeof nm, "path %d 延迟", p);
            report(nm, labs((long)at - want[p]) <= TOL_DELAY_ERR,
                   "峰值在第 %zu 点，应为 %d 点（%.0f ms）",
                   at, want[p], want[p] * 1000.0 / ECG_FS);
        }
    }

    // ── 汇总 ──
    printf("\n==================================================\n");
    if (g_fail == 0) {
        printf("全部通过\n");
        return 0;
    }
    printf("%d 项未通过\n", g_fail);
    return 1;
}

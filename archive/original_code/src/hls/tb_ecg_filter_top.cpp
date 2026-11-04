// tb_ecg_filter_top.cpp —— Vitis HLS 的 csim / cosim 测试平台
//
// 和 tb_ecg_filter.cpp 的分工：
//   tb_ecg_filter.cpp      驱动纯 C 核心，g++ 秒级跑完，做五项详细检查
//                          （黄金比对 / 冲激 / 50Hz / 位宽核对 / 通路延迟）
//   tb_ecg_filter_top.cpp  驱动 AXI 顶层，用于 csim 与 cosim，
//                          验证"加了接口和约束之后行为没变"
//
// cosim 很慢：每采样点约 344 次串行乘法，2000 点 ≈ 70 万周期的 RTL 仿真。
// 所以点数可配：
//   csim   用全长（30034 点）
//   cosim  编译时加 -DN_SIM=2000，几分钟能出结果
//
// 数据目录由 TCL 用 -DECG_DATA_DIR 传绝对路径进来，
// 因为 Vitis HLS 的 csim 工作目录在 <project>/<solution>/csim/build。

#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>
#include <string>
#include "ecg_filter.h"

#ifndef ECG_DATA_DIR
#define ECG_DATA_DIR "data"
#endif
#ifndef N_SIM
#define N_SIM 0            // 0 = 用向量全长
#endif

#define TOL_MAX_LSB 64.0
#define TOL_RMS_LSB 8.0

void ecg_filter_top(const int32_t *in, int32_t *out,
                    int32_t n_samples, int32_t do_reset);

// 向上逐级找 data/ 目录 —— Vitis HLS 的 csim 工作目录在
// <project>/<solution>/csim/build，相对路径指不到工程根。
// 这样无需靠 -D 传路径（TCL 里转义引号很容易出错），从任何目录启动都能跑。
static bool load_txt(const char *name, std::vector<double> &v)
{
    FILE *f = 0;
    std::string hit;
    std::string up;
    for (int lvl = 0; lvl < 10 && !f; lvl++) {
        hit = up + std::string(ECG_DATA_DIR) + "/" + name;
        f = fopen(hit.c_str(), "r");
        up += "../";
    }
    if (!f) {
        printf("  找不到 %s（已从当前目录向上找 10 级的 %s/）\n",
               name, ECG_DATA_DIR);
        return false;
    }
    v.clear();
    char line[128];
    while (fgets(line, sizeof line, f)) {
        char *e; double x = strtod(line, &e);
        if (e != line) v.push_back(x);
    }
    fclose(f);
    return !v.empty();
}

int main()
{
    printf("======== ecg_filter_top csim / cosim ========\n");
    std::vector<double> raw, gold;
    if (!load_txt("input_raw.txt", raw) || !load_txt("golden_float.txt", gold)) {
        printf("读不到测试向量，先跑 python sim/gen_vectors.py\n");
        return 1;
    }

    size_t n = raw.size();
    if (N_SIM > 0 && (size_t)N_SIM < n) n = N_SIM;
    printf("处理 %zu 个采样点 x %d 通道，共 %zu 个样本\n",
           n, N_CHANNELS, n * N_CHANNELS);

    // 8 个通道喂同一份数据：这样每个通道的输出都该和黄金参考一致，
    // 顺带验证"通道之间状态没有串扰"
    std::vector<int32_t> in(n * N_CHANNELS);
    std::vector<int32_t> out(n * N_CHANNELS * N_PATHS, 0);
    for (size_t i = 0; i < n; i++)
        for (int ch = 0; ch < N_CHANNELS; ch++)
            in[i * N_CHANNELS + ch] = (int32_t)llround(raw[i]);

    ecg_filter_top(&in[0], &out[0], (int32_t)n, 1);

    int fail = 0;

    // ── ① 诊断通路（path 0）对黄金参考 ──
    {
        double mx = 0, s2 = 0; size_t cnt = 0, at = 0;
        for (size_t i = ECG_WARMUP; i < n; i++) {
            double e = fabs((double)out[(i * N_CHANNELS + 0) * N_PATHS + 0] - gold[i]);
            if (e > mx) { mx = e; at = i; }
            s2 += e * e; cnt++;
        }
        double rms = cnt ? sqrt(s2 / cnt) : 0;
        bool ok = (mx <= TOL_MAX_LSB) && (rms <= TOL_RMS_LSB);
        printf("  [%s] ch0 path0 对黄金参考：最大 %.1f 码（第 %zu 点），RMS %.3f 码，比较 %zu 点\n",
               ok ? "通过" : "失败", mx, at, rms, cnt);
        if (!ok) fail++;
    }

    // ── ② 通道之间是否串扰 ──
    // 8 个通道输入相同，输出必须逐点完全相同（延迟配置相同的通道之间）
    {
        int bad = 0;
        for (size_t i = 0; i < n && bad == 0; i++)
            for (int ch = 1; ch < N_CHANNELS; ch++)
                if (DC_DELAY_CFG[ch][0] == DC_DELAY_CFG[0][0] &&
                    out[(i * N_CHANNELS + ch) * N_PATHS + 0] !=
                    out[(i * N_CHANNELS + 0) * N_PATHS + 0]) { bad++; break; }
        printf("  [%s] 通道间无串扰（同延迟配置的通道输出逐点相同）\n",
               bad ? "失败" : "通过");
        if (bad) fail++;
    }

    // ── ③ 每条通路的延迟是不是 DC_DELAY_CFG 说的那个 ──
    // 注意：两条通路不是"同一个滤波器平移"，而是两个不同的滤波器 ——
    //   path0 算 yg[n-D0] - lp[n]，path1 算 yg[n-D1] - lp[n]，
    //   减的是**同一时刻**的基线估计，所以把 path0 推迟 D0-D1 点并不会和 path1 重合。
    //   这条注释来自一次写错的检查：最初按"平移后应当一致"去测，实测差 11460 码
    //   （= 基线在 318 ms 内的移动量），查出来是测试的心智模型错了，不是设计错了。
    // 真正该测的是冲激响应的峰值位置。
    {
        const size_t NI = 1024;
        std::vector<int32_t> ii(NI * N_CHANNELS, 0);
        std::vector<int32_t> io(NI * N_CHANNELS * N_PATHS, 0);
        for (int ch = 0; ch < N_CHANNELS; ch++)
            ii[0 * N_CHANNELS + ch] = (1 << 20);
        ecg_filter_top(&ii[0], &io[0], (int32_t)NI, 1);

        for (int p = 0; p < N_PATHS; p++) {
            int want = DC_DELAY_CFG[0][p] + FIR_DELAY;
            size_t at = 0; double pk = 0;
            for (size_t i = 0; i < NI; i++) {
                double v = fabs((double)io[(i * N_CHANNELS + 0) * N_PATHS + p]);
                if (v > pk) { pk = v; at = i; }
            }
            bool ok = ((long)at == (long)want);
            printf("  [%s] ch0 path%d 延迟：峰值在第 %zu 点，应为 %d 点（%.0f ms）\n",
                   ok ? "通过" : "失败", p, at, want, want * 1000.0 / ECG_FS);
            if (!ok) fail++;
        }

        // ch2 被配成两路都走低延迟，它的 path0 应当落在 DC_DELAY_FAST —— 验逐通道配置生效
        int want2 = DC_DELAY_CFG[2][0] + FIR_DELAY;
        size_t at2 = 0; double pk2 = 0;
        for (size_t i = 0; i < NI; i++) {
            double v = fabs((double)io[(i * N_CHANNELS + 2) * N_PATHS + 0]);
            if (v > pk2) { pk2 = v; at2 = i; }
        }
        bool ok2 = ((long)at2 == (long)want2);
        printf("  [%s] ch2 path0 延迟：峰值在第 %zu 点，应为 %d 点（逐通道配置生效）\n",
               ok2 ? "通过" : "失败", at2, want2);
        if (!ok2) fail++;
    }

    printf("=============================================\n");
    printf("%s\n", fail ? "有检查未通过" : "全部通过");
    return fail ? 1 : 0;
}

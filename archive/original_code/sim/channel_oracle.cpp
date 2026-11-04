// Test-only host oracle: each channel is evaluated separately, without the AXI wrapper.
#include "../src/hls/ecg_filter.h"
#include <fstream>
#include <vector>
#include <iostream>
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::ifstream f(argv[1], std::ios::binary | std::ios::ate);
    if (!f) return 3;
    auto bytes = f.tellg();
    if (bytes <= 0 || bytes % (8 * sizeof(int32_t))) return 4;
    std::vector<int32_t> x(static_cast<size_t>(bytes) / sizeof(int32_t));
    f.seekg(0); f.read(reinterpret_cast<char *>(x.data()), bytes);
    if (!f) return 5;
    const size_t n = x.size() / 8;
    std::vector<int32_t> y(n * 8 * 2);
    ecg_range_t ranges; ecg_range_init(&ranges);
    for (int ch = 0; ch < 8; ++ch) {
        ecg_chan_state_t state;
        ecg_filter_init(&state, DC_DELAY_CFG[ch]);
        for (size_t i = 0; i < n; ++i) {
            ecg_sample_t out[2];
            ecg_filter_sample(&state, x[i * 8 + ch], out, &ranges);
            for (int p = 0; p < 2; ++p) y[(i * 8 + ch) * 2 + p] = out[p];
        }
    }
    // Keep this bounded-amplitude test inside the actual hardware widths.
    if (ranges.max_abs_yg >= (1LL<<23) || ranges.max_abs_dcout >= (1LL<<23) ||
        ranges.max_abs_out >= (1LL<<23) || ranges.max_abs_boxsum >= (1LL<<33) ||
        ranges.max_abs_notchacc >= (1LL<<47) || ranges.max_abs_firacc >= (1LL<<47)) return 6;
    std::ofstream g(argv[2], std::ios::binary);
    g.write(reinterpret_cast<const char *>(y.data()), y.size() * sizeof(int32_t));
    if (!g) return 7;
    std::cout << "ORACLE_PASS samples=" << n << " max_output=" << ranges.max_abs_out << "\n";
}

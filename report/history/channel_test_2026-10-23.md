# 不同通道激励与隔离测试

日期：2026-10-23。真实 PYNQ-Z2 上完成 **20 项检查，全通过**。使用已验证的修复版滤波 overlay，bit SHA256 `78b5b1d4bae005aadf9635c8832a71f418f2394d5e21ec14d3b79ceb64986be5`。没有改动算法、系数或重新生成滤波比特流。

## 输入与比较方法

`sim/gen_channel_vectors.py` 生成固定随机种子的4096点 × 8通道有符号整数向量，输入峰值120,000码。ch0为双极性冲激，ch1为5Hz正弦，ch2为17Hz正弦，ch3为阶跃，ch4为50Hz正弦，ch5为有界随机信号，ch6为周期脉冲，ch7在混合测试中为零。

`sim/channel_oracle.cpp` 在主机上调用同一份定点核心，对各通道单独初始化、逐通道计算，生成预期输出；不通过 AXI 顶层。范围统计确认这些测试向量处于声明的样本、滑动和及累加器位宽内。这是硬件对定点核心的一致性检查，不是另一套独立浮点算法的精度评价。

板上脚本为 `board/test_channel_isolation.py`。所有点都比较，包括启动阶段；不丢弃543点。

| 检查 | 结果 |
|---|---|
| 八通道不同输入，对主机定点核心 | 全部 `[4096,8,2]` 输出逐点一致，最大误差0码 |
| 混合输入中的零哨兵通道ch7 | 两条通路全零 |
| 不规则分块 `[1,7,319,320,321,500,997]` | 与单个4096点块完全一致 |
| 逐个通道单独激励，其他7通道保持零 | 8组测试的未激励通道、两条通路全部为零 |
| 单独激励时的活动通道输出 | ch0～6与混合测试对应通道逐点一致 |
| ch7单独激励 | 使用ch5相同输入；因两者延迟配置相同，输出与混合测试ch5逐点一致 |
| 多条记录之后重新复位回放 | 与首轮混合测试逐点一致 |

结果为 `CHANNEL_TEST_PASS 20`。板上数据位于 `/home/xilinx/jupyter_notebooks/ecg_channel_test_20261023/board/channel_test_results/`，测试单元格追加于已有 `ECG_FPGA_ResetFix_Verification_20261022.ipynb`。

## 本机证据

- `board/results/ecg_channel_results_20261023.zip`，SHA256 `8f0bcaea775b17b87aa2dd5f847541ef192b393863e32c951d73d22c8d11d0b8`。
- 解包目录 `board/results/channel_test_20261023/`：20项检查、summary、真实混合输入输出 NPY、截图和取回复核记录。
- 归档与板上哈希一致、ZIP完整性通过；从本机落盘NPY再次与主机预期比较，最大误差仍为0码。

可复现：在主机运行 `sim/gen_channel_vectors.py`，编译并运行 `sim/channel_oracle.cpp` 与 `src/hls/ecg_filter.cpp` 生成预期二进制；将 `board/test_channel_isolation.py` 和 `board/channel_test/` 复制到板上，运行脚本并指定 `--overlay` 为修复版 bit 路径。

## 结论边界

这次验证补齐了不同输入及所有八个通道的单通道激励测试，在这些向量下未发现数字滤波通道串扰。它不证明所有可能输入／满量程溢出场景都正确，也不测试 ADS1292 的模拟通道串扰、电极接触、SPI电气时序或真实采样完整性。

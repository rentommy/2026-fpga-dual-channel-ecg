# Vivado 集成与实现结果

原记录日期：2026-10-22；最新更新：2026-10-23。本文保留首次实现及复位故障记录，并纳入修复后的真实板上结果。完整进度见 [项目进度与接手结论](project_progress_2026-10-23.md)。

## 已完成

- 通过 Computer Use 连接并实际操作用户已打开的 Vivado 2026.1 窗口。
- 下载并核对 TUL 厂商 PYNQ-Z2 板级配置，将其保存在项目内，未修改工具安装目录。
- 建立 PS + HLS 滤波核 + 三个 SmartConnect + 时钟复位的最小文件回放系统。
- 连接通过 `validate_bd_design`，生成顶层封装。
- 完成 IP 综合、顶层综合、布局、布线、比特流生成。
- 导出匹配的 `board/overlay/ecg_filter.bit` 与 `ecg_filter.hwh`。
- 使用 Vitis 2026.1 跑通精确位宽 C 仿真，并验证新增的可复现入口 `sim/run_csim_2026.tcl`。
- 定位并修复辅助复位极性错误，重新完成综合、实现与比特流生成。
- 在 PYNQ-Z2 上通过控制访问、单点处理及完整记录回放；500／4096 点分块输出逐点完全一致。

当前已跑通“PS 文件输入 → DDR → PL 滤波 → DDR → PS 数值比对”的最小板上链路。实时 ADS1292 采集、显示与模型应用尚未闭环。

## 实现证据

| 项目 | 结果 |
|---|---|
| 工具 | Vivado 2026.1，Build 6511674 |
| 器件 | xc7z020clg400-1 |
| 当前有效工程 | `build/vivado/ecg_overlay_resetfix/ecg_overlay.xpr` |
| 顶层 | `ecg_system_wrapper` |
| PL 时钟 | 100 MHz，周期 10 ns |
| 布线后 WNS | +0.076 ns |
| 布线后 WHS | +0.024 ns |
| Setup／Hold 失败端点 | 均为零 |
| 无时钟／内部未约束端点 | 均为零 |
| DSP | 1 / 220，0.45% |
| LUT | 5,208 / 53,200，9.79% |
| 触发器 | 8,294 / 106,400，7.80% |
| Block RAM Tile | 12.5 / 140，8.93%，等效 25 块 BRAM18K |
| 比特流 | `Bitgen Completed Successfully` |

以上是整套系统的实际实现报告，包含接口和互连，统计口径不同于 HLS 对单核的估计。不能继续把 HLS 的 136.99 MHz 估计当成实际系统运行频率。

`board/overlay/timing_summary.rpt` 明确给出全部用户时序约束满足；`utilization.rpt` 给出实现后的资源；`drc.rpt` 保留设计规则检查结果。

实现后 DRC 没有 Error 或 Critical Warning，仍有六项 Warning，集中于 DSP 的输入／输出流水建议及动态 OPMODE 检查。综合日志将该 DSP 的实际运算识别为 `(C or 0)+A*B`，不是据此认定存在 P 自反馈。没有关闭或降级这些检查；其原文留在报告中。本次文件回放已通过数值比对，但不代表所有异常输入均已覆盖。

## C 仿真

新的批处理入口使用 `open_component`，并让组件父目录与工作目录一致，避免此前旧流程的设计文件路径问题。

工具实际编译了核心、顶层和测试平台三份源文件，包含 `ap_int.h` 的精确位宽分支。处理 30,034 点 × 八通道；诊断通路跳过前 543 点后最大误差 3.3 码、RMS 0.698 码。通道一致性与 174／15 点冲激峰值检查通过，日志为 `CSim done with 0 errors`，进程退出码为零。

可复现命令（项目根目录，在有工具环境的命令行执行）：

```text
vitis-run --mode hls --tcl sim/run_csim_2026.tcl
```

结果在 `build/hls_csim/ecg_csim/hls/csim/`。C/RTL 协同仿真尚未运行，C 仿真通过不等于 RTL 或板上验证通过。

## 接口与板上验证入口

控制地址为 `0x40000000`，输入／输出 DDR 分别经过 HP0／HP1。当前采用轮询完成状态，不使用中断，不需要额外 AXI DMA。内存布局保持八通道、两通路，算法、系数及滤波核源码未修改。

`board/verify_overlay.py` 按块送入完整测试记录，仅第一块复位，管理缓存同步并对诊断输出与黄金参考做比较。语法检查、`--help` 及修复后的真实板上执行均已通过。首次板上启动曾导致 Jupyter 停止响应，故障与修复证据见下文。

## 首次板上尝试：未完成

已通过用户提供的 Jupyter 地址连接真实板卡。Python 输出确认 `BOARD: Pynq-Z2`、活动设备 `Pynq-Z2`、PYNQ 3.1.1、Python 3.10.4、`armv7l`，此前 overlay 为 `None`。可选设备信息 `/proc/device-tree/model` 不存在；改用 PYNQ 活动设备信息完成确认。

验证包已上传并解压至 `/home/xilinx/jupyter_notebooks/ecg_validation_20261022`。板上计算的 `.bit` 和 `.hwh` SHA256 与本机清单一致。启动 `%run ecg_validation_20261022/board/verify_overlay.py` 后，没有取得完成输出；Notebook 保持忙碌，另一次保存请求也未返回并显示自动保存失败。独立检查发现 TCP 9090 可连接，但 `/login` HTTP 请求在 5 秒内未返回。

当时只能确认回放未完成，尚不能确定卡住环节。随后用户断电重启恢复，使用新增的 `board/probe_overlay.py` 分 parse、load、control、sample 四阶段定位，在关键步骤前后将日志同步写盘。首次现场截图保存在 `board/results/jupyter_stalled_20261022.jpg`。首次 Notebook 曾保存失败，不能把当时未保存的页面内容视为持久证据。

## 复位故障定位与修复

环境检查、`Overlay(..., download=False)` 元数据解析和单独 `overlay.download()` 均完成；设备返回 `loaded: true`。随后 control 阶段在加载完成附近再次停止返回，未取得控制寄存器的值。解析及加载结果保存在板上诊断日志 `board/overlay/probe_trace.jsonl`，每一步均同步写盘。

本机检查生成的 HWH 与复位 IP 仿真网表，发现首版复位接线存在明确错误：`C_AUX_RESET_HIGH=0`，`aux_reset_in` 为 `ACTIVE_LOW`，却接到了 `const_zero_dout`。仿真网表的 `ACTIVE_LOW_AUX` 反相器进一步确认低电平会触发复位；因此总线与滤波核被持续复位，控制访问可能无法返回。

修复将辅助复位显式配置为高电平有效并保留接地；外部复位仍接 PS 的 `FCLK_RESET0_N`，低电平有效。创建脚本增加极性断言。独立修复工程为 `build/vivado/ecg_overlay_resetfix/ecg_overlay.xpr`，批处理入口 `board/build_resetfix.tcl`；旧产物已归档至 `board/results/first_reset_fault/`。新 HWH 已确认 `C_AUX_RESET_HIGH=1`、`ACTIVE_HIGH`，重新构建与时序检查通过，资源和时序指标见上表。

修复版 `.bit` SHA256：`78b5b1d4bae005aadf9635c8832a71f418f2394d5e21ec14d3b79ceb64986be5`。

修复版 `.hwh` SHA256：`f3f2e48f84e1b56849b48068fc632547270a00a28a14f5f3a5cc6ad37e4459cd`。

## 修复后的板上验证：通过

板上运行环境为 PYNQ-Z2、PYNQ 3.1.1、Python 3.10.4。修复包解压于 `/home/xilinx/jupyter_notebooks/ecg_validation_resetfix_20261022`，板上重算的 bit／hwh 哈希与本机一致。`ECG_FPGA_ResetFix_Verification_20261022.ipynb` 已自动保存。

控制阶段读回 `0x4`，表示滤波核空闲。单点阶段完成 DDR 分配、缓存同步、物理地址配置、启动和完成检测；复位后的零输入得到八通道、两通路全零输出。先前控制访问卡住的问题在修复版中已消除。

完整测试使用同一份 30,034 点单列记录复制到八个逻辑通道。仅首块复位，跳过前 543 点后，将 ch0、ch1、ch4、ch5、ch6、ch7 的诊断通路与浮点黄金参考比较；ch2、ch3 的 path 0 按配置为低延迟通路，不纳入该诊断参考比较。

| 检查 | 500 点分块 | 4096 点分块 |
|---|---:|---:|
| 每通道输入长度 | 30,034 点 | 30,034 点 |
| 比较长度 | 29,491 点 | 29,491 点 |
| 最大绝对误差 | 3.28984 码 | 3.28984 码 |
| RMS 误差 | 0.698013 码 | 0.698013 码 |
| 最大单块墙钟时间 | 6.740013 ms | 53.397889 ms |
| 脚本验收结果 | PASS | PASS |

两次输出均为 `[30034, 8, 2]`，`np.array_equal` 检查全部输出逐点完全一致。这验证了该记录在这两种分块方式下的状态保持与输出一致性。墙钟时间包含 PS 轮询及主机开销，不能作为实时显示或端到端采集延迟。

板上结果已于 2026-10-23 取回本机，压缩包为 ecg_board_results_resetfix_20261022.zip（原工作区引用：`../board/results/ecg_board_results_resetfix_20261022.zip`，未随此公共候选发布），共 447,965 字节，SHA256 为 `c5ae5f12fbf490743daabf86f0c9ee7fe47e5cd6774c5248cf5fee6848fde996`，与板上归档完全匹配，ZIP 完整性检查通过。

解包目录为 `board/results/resetfix/`，包含两份 NPY 输出及误差 JSON、`board_validation_summary.json`、修复前后诊断日志，以及板上 `build_manifest.json` 快照。从本机落盘的 NPY 重新计算得到最大误差 3.289839999999913 码、RMS 0.6980127934805861 码，两分块 `np.array_equal` 仍为真；取回与复核记录见 retrieval_receipt.json（原工作区引用：`../board/results/resetfix/retrieval_receipt.json`，未随此公共候选发布）。

板卡系统时钟停留在 2025-05-04，因此诊断日志中的 `time` 值只能按原样保留，不能作为本次操作的真实日历日期。本次取回日期以客户端日期 2026-10-23 为准。

本次测试没有证明任意不同通道激励下的隔离，也未接入实时采集或运行分类模型；这些仍是后续任务。

## 仍未完成

- 不同通道激励现已通过20项板上检查，见 [通道测试](channel_test_2026-10-23.md)；满量程／异常输入覆盖仍待补充。
- C/RTL 协同仿真及需要补充的复位／异常边界测试。
- ADS1292 实时采集接入及完整显示／推理应用。
- 电极状态与异常恢复、模型预处理一致性、独立采集数据。
- 通用技能包与最终竞赛材料。

首次接手报告中的“没有 bit/hwh”“Vivado 未完成”“Vitis C 仿真无通过证据”，应作为当时快照理解；当前状态以本记录及实际产物为准。

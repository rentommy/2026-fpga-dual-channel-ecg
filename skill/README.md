# 可复用技能包

本包来自本项目的失败与修正，面向其他 AXI/PYNQ/HLS 题目，不依赖心电算法。

| 工具/经验 | 场景与使用方法 | 来源与已验证效果 | 失效条件 |
|---|---|---|---|
| `report_gate.py` | `python skill/report_gate.py build/reports/timing_summary.rpt` | 初版布局布线存在负余量，修复后读取实际WNS/WHS；正、负、缺失报告均有自测 | 仅适配Vivado标准时序汇总表。报告格式不匹配就报错，不能把空报告当通过。不能替代CDC/DRC和现场验证 |
| `overlay_check.py` | 板端 `sudo python skill/overlay_check.py --overlay board/runtime/overlay/ecg_inference.bit --ip ecg_io --expected 0x45434736` | 多次固件ABI升级要求软件配套。模拟正确/错误ABI均验证；项目ScopeIO运行时使用同一类检查 | 依赖有效HWH和可读寄存器。IP名、偏移、期望值必须来自自己的接口契约。禁止对未响应总线盲读；不下载bit、不抢占采集 |
| 缓存所有权与异常退出清单 | 见下文 | PynqBuffer子类进入后处理后曾在清理路径出现SEGV，显式普通数组复制后完成49拍回放 | 不能泛化成所有崩溃均为缓存问题，也不能覆盖硬件尚未完成时释放缓冲区 |

自测：`python skill/report_gate.py --selftest`、`python skill/overlay_check.py --selftest`。报告解析另有 `sim/collect_hls_report.py --selftest`，支持别的HLS工程，不把整块延迟冒充每点延迟。

## PYNQ 缓存与错误定位工作流

1. 写入DMA输入后flush，硬件完成后invalidate输出；只在确认完成之后读取。
2. 若下游需要跨硬件缓冲区生命周期保存数据，使用 `np.array(buf, copy=True, subok=False)`，明确所有权。
3. 单个进程独占Overlay与采集控制，子进程仅连接自己负责的IP；用进程锁防止Notebook和服务同时抢占。
4. 停止生产者、等待硬件事务结束，再释放缓冲区；异常追踪不能长期持有已经释放的缓冲区视图。
5. 通信ID异常、DRDY停止、无效帧先分别记录，不把电源脱落归因于算法；先定位，再修改一个变量做对照。

来源：`report/history/monitoring_2026-11-04.md`、`report/llm_log/2026-11-04.md`、`report/history/dual_view_acquisition_followup_2026-11-04.md`。经验适用于缓存与AXI控制场景，新的板卡/驱动版本仍需重新验证。

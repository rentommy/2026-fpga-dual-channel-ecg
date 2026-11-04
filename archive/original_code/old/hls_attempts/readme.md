# HLS历史尝试

2026-10-23从项目根目录原样移入，内容和字节校验和保留。这些文件用于追溯10-21至10-22工具链调试，不是推荐运行入口；部分包含原机器绝对路径，部分会重建旧组件。不要批量执行本目录脚本。

| 文件 | 当时用途／结果 |
|---|---|
| `hls_run1.tcl` | 清空argv后调用旧run_hls入口；历史C仿真链接失败 |
| `hls_test.tcl` | 去除cflags的C仿真对照，仍链接失败 |
| `hls_syn.tcl` | 旧工程流程综合，找不到设计源文件 |
| `hls_syn2.tcl` | 组件放到build子目录的试验，仍有路径问题 |
| `hls_syn3.tcl` | 最终完成首版综合，但产出304 DSP、LUT超限的旧实现 |
| `t_a.tcl` | open_project与相对路径试验，未解决路径问题 |
| `t_b.tcl` | open_component试验，开始分析源码后遇到ap_int类型歧义 |

实际成功的单DSP综合及导出入口分别在 [hls_fix.tcl](../../src/hls/hls_fix.tcl) 与 [hls_export.tcl](../../src/hls/hls_export.tcl)。这些有效入口仍输出根目录 `hls_ecg2/`，以兼容现有Vivado引用。

详细过程见[10-21协作补记](../../report/llm_log/2026-10-21.md)、[10-22协作补记](../../report/llm_log/2026-10-22.md)。原始日志留在 `logs/`；移动记录及校验和见 `report/organization_2026-10-23.json`。

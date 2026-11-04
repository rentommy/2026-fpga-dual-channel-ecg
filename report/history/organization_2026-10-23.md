# 项目根目录整理

整理日期：2026-10-23。用户要求将直接放在 `D:/ecg_fpga` 的散落文件归类，保留项目可运行性。

## 移动清单

| 原位置（相对项目根） | 新位置 | 用途 |
|---|---|---|
| hls_fix.tcl | src/hls/hls_fix.tcl | 当前单DSP综合入口 |
| hls_export.tcl | src/hls/hls_export.tcl | 当前单DSP综合与IP导出入口 |
| hls_run1.tcl | old/hls_attempts/hls_run1.tcl | 历史argv／旧入口试验 |
| hls_test.tcl | old/hls_attempts/hls_test.tcl | 历史C仿真试验 |
| hls_syn.tcl | old/hls_attempts/hls_syn.tcl | 历史综合路径试验 |
| hls_syn2.tcl | old/hls_attempts/hls_syn2.tcl | 历史组件目录试验 |
| hls_syn3.tcl | old/hls_attempts/hls_syn3.tcl | 首版资源超限实现入口 |
| t_a.tcl | old/hls_attempts/t_a.tcl | 旧工程流程对照 |
| t_b.tcl | old/hls_attempts/t_b.tcl | 组件流程对照 |
| NA/ps7_summary.html | build/reports/ps7_summary.html | 工具生成的PS7配置报告 |

空的NA目录已移除。根目录常规文件现仅有README.md、LICENSE、.gitignore。没有删除历史脚本、工具日志或构建证据。

## 路径和说明更新

两个有效入口增加从 `[info script]` 计算项目根目录并切换工作目录的三行前缀，原有设计文件、器件、时钟、单DSP约束、综合和导出命令保持原样。这样脚本移入src/hls后，从其他工作目录按绝对路径调用仍输出原来的hls_ecg2组件。

主README、HLS接口说明、board构建说明及当前进度已更新为新入口。旧接手快照增加路径迁移说明，原始Claude转录和工具日志不改写，历史文件名仍代表当时位置。归档目录新增README区分失败与资源超限的历史结果。

## 保持位置的工具目录

- `hls_ecg2/`：已导出的有效IP被Vivado工程、board创建脚本和结果清单引用，保留原位。
- `hls_ecg/`、`hls_b/`：历史组件含相对源文件路径，保留原位作为证据，不能只拖进build后假定可继续打开。
- `.Xil/`：工具缓存按工具管理，本次不处理正在使用与否未知的缓存。
- 采集板、隔离板、旧资料和STM32原工程保留用户现有目录。

## 校验范围

移动前记录文件SHA256及36个受保护文件的校验和，包含HLS／RTL源码、数据、模型、网表、有效IP、bit／hwh、发布包及原始对话。移动后核对内容；历史脚本与PS7报告应逐字节不变，两个有效入口只允许增加定位根目录的前缀。

从非项目根目录进行Tcl空操作检查，仅将HLS命令替换为记录调用的占位过程，验证实际Tcl路径计算、源文件存在及原单DSP指令保留。不运行HLS综合／导出，也不触碰现有组件、Vivado工程或板卡。

最终检查结果及前后哈希见 organization_2026-10-23.json（原工作区引用：`organization_2026-10-23.json`，未随此公共候选发布）。

本次检查通过：10个文件已归位，历史脚本和HTML逐字节一致；两个有效入口的原命令正文逐字节一致，仅增加三行定位前缀；35个受保护文件哈希未变化，另1个为有意更新入口说明的INTERFACE.md。32处相对文档链接有效。源码、数据、模型、网表、有效IP、bit／hwh及发布包未变化，未重新综合或上板。

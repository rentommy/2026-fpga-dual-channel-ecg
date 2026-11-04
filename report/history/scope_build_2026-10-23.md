# Pmod A 采集与 HDMI 波形版本进度

新产物为 `board/scope/ecg_scope.bit` 和同名 `.hwh`，板卡为PYNQ-Z2，Vivado 2026.1。原文件回放版仍在 `board/overlay/`。本次未改变滤波算法。

## 已完成

- 新增Mode 1 SPI主机、手动寄存器交易、DRDY自动读取、24位状态及双通道数据、1024帧FIFO、丢帧及坏帧计数。Pmod A固定分配见使用指南；约561.798kHz SCLK，500SPS。
- 新增640×480@60Hz视频、四秒波形窗口、两个物理通道和两种滤波通路、自动纵轴。BTN0/1选择CH1/2，BTN2切通路，BTN3冻结显示。视频通过HDMI OUT输出，无音频。
- SPI、FIFO、AXI读写、按键消抖自检通过；视频仿真验证完整帧、通道／通路／冻结选择，保存两张RTL预览。
- 最终布局布线setup余量+0.041ns、hold余量+0.023ns，负slack端点0，无时钟端点0，内部未约束端点0。6751 LUT、9665 FF、1 DSP、17 BRAM Tile。
- DRC无Error／Critical Warning，保留6项DSP流水建议和2项BUFG连接Warning。CDC报告5条已同步UI跨时钟路径、unsafe为0。外部异步输入仍有7项no_input_delay、4项SPI输出no_output_delay；输出有20ns最大数据路径边界，不能替代实际隔离器时序校核。
- 新比特流已上板：30034点×8通道×2通路回放通过，最大误差3.28984码、RMS 0.698012793码。新增AXI标识和8种UI状态读写通过。演示两路各4000点，8.0003秒，程序无错误。

## 尚待硬件验收

用户确认隔离器HOST侧未设计、显示器未购置。因此真实ADC、隔离器电气时序、物理按键实按及显示器画面尚未验收。演示采集为合成数据，零溢出不能证明真实ADC链路。

HPD本次读值为1，尽管没有显示器，因此仅记录该原始值，不据此判定连接或视频成功。用户之后应接显示器到HDMI OUT并运行演示，再验证按键，最后连接隔离板并从ADC内部测试信号开始。

板卡系统日期仍为2025年，实际执行日期为本报告日期。实测原始摘要及截图在 `board/scope/board_acceptance.json/.png`；文件校验清单在 `board/scope/build_manifest.json`。

构建入口 `board/build_scope.tcl`，已存在工程使用 `board/resume_scope_build.tcl`；导出前若setup不满足，会进行AggressiveExplore物理优化与Explore重布线，仍失败则拒绝导出。当前最终产物来自 `board/close_scope_timing.tcl`，日志 `build/scope_timing_closure.log`。BD可复现文件已从保存工程重新导出。

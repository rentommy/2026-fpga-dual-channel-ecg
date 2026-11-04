# 识别标签滚动卡顿修复

用户观察：识别字母移动明显比波形卡顿。

根因：旧软件把标签横坐标强制取整到16像素文字格，RTL又按屏幕绝对坐标取字形列。4秒/640像素窗口的滚动速度为160像素/秒，标签约每0.1秒跳16像素，即使波形每秒更新约29次，标签仍只有约10次明显位置变化。

修复：标签缓存由每列8位ASCII改为12位 `{字形内部横坐标[3:0], ASCII[7:0]}`，RTL依据局部横坐标绘制。ARM取消16像素对齐，横坐标精确到1像素，使用预计算的字形列编码减少逐帧分配开销。波形与标签沿用同一双缓冲，在垂直消隐同时换帧。REPLAY/ERROR也使用配套编码。标签从屏幕边缘滑出时保留正确裁剪相位。

同时避免将重新检测到的轻微偏移R峰作为新的问号，覆盖已经确认的分类标签。已确认标签的时间锚点保持不变，随波形滚动。

接口升级为 **ECG4 / 0x45434734**，软件与比特流必须配套。卷积、模型权重、RR及心拍预处理没有变更。

验证：

- 软件测试覆盖656个横向起始位置与左右边缘裁剪；30 FPS对应采样步长下每帧移动5–6像素，跨文字格不跳位；待识别峰微抖不覆盖确认标签。
- RTL仿真逐像素检查从非对齐坐标x=37开始的完整N字形，双缓冲及消隐换帧通过。
- SPI/FIFO/按钮/ABI/写保护回归仿真通过。
- 新固件最终时序通过：WNS +0.001 ns，WHS +0.051 ns，无失败端点。LUT 15,607、FF 20,463、BRAM Tile 59、DSP 57。
- 新固件上重新执行49拍、588次FPGA卷积调用，分类49/49与PyTorch参考一致，最大logit误差0.000002384；每拍平均138.35 ms。数值一致性不等于临床准确率。

新板端目录：`/home/xilinx/jupyter_notebooks/ecg_inference_smooth_20261104`。服务保持用户修改前的记录回放模式及启动通道，并更新自启动路径。

部署包：`board/ecg_inference_smooth_20261104.zip`。

部署包SHA256：`9228d1e69a8a5b0d01f64aa79eae18af614a823bf88f39f739f383f822ccc4d0`。

新比特流SHA256：`2d70e2044d3e83bd07176d12198a384e2175539e1f5a146444eb15ac4dd3b0a8`。

本机旧版备份：`board/inference_before_smooth_20261104/`。板上旧运行目录及旧部署包保留；新目录的`ecg-scope.service.before-smooth`保存升级前服务，必要时停止服务并将其复制回`/etc/systemd/system/ecg-scope.service`，执行daemon-reload及restart即可回退。不要将新版Python脚本单独配旧比特流。

日志：`logs/smooth_labels_build_20261104.log`、`logs/smooth_label_video_sim.log`、`logs/smooth_label_io_sim.log`。构建入口：`board/build_smooth_labels.tcl`。

板端稳定运行快照：服务PID 5358，更新率约29 FPS，推理worker存活、无推理错误，ECG4 ABI与板上像素编码检查通过。完整板端结果已保存到`report/label_smooth_20261104/board_verification.json`，数值测试另存为该目录的`fpga_replay_results.json`。

用户查看HDMI后的现场反馈为“已经平滑，和波形接近”。本次标签滚动修复的实际观感已确认；当前仍为记录回放模式。

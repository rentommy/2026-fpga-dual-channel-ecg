# FPGA 卷积部署与真实心电推理实测

同日后续：用户反馈标签移动卡顿，已升级ECG4像素定位版本，当前部署路径与新固件信息见[标签平滑修复记录](label_smooth_2026-11-04.md)。下文保留首版ECG3部署的测量与归档；新版本需要配套新Python脚本。

更新：2026-11-04。已部署并在 PYNQ-Z2 上完成文件回放推理；当前自启动使用真实记录回放。用户现场没有连接 ADS1292 和 HDMI 采集卡，因此本次没有验证实时电极推理或实际 HDMI 画面。此前实时采集与 HDMI 的验证记录继续保留，不等同于本次新固件的实物验收。

## 部署内容

- 全部 **12 个 Conv1d 层**由 FPGA 的 FP32 卷积加速器执行，未量化、未改训练权重。
- ARM 执行 R 峰定位、RR 特征、GroupNorm、门控、全连接与推理调度。无需在板上安装 PyTorch。
- HDMI 保持实时滚动的4秒波形窗口，模型结果延后回填到对应心拍上方。问号表示等待，字母是模型标签。显示路径的固定延迟分别补偿174点和15点；复杂波形下的视觉对齐仍需现场检查。
- 使用独立推理进程及有界队列。波形显示不等待模型完成；错误写入状态文件，并在标签区显示 ERROR。
- 回放模式固定显示 **REPLAY**；通道1来自 CN4 记录，通道2来自 CN2 记录，两次独立采集不是同步双导联。

## 选定模型与输入

权重：`模型训练/模型改进/experiment_09/runs/six_db_seed0/best.pt`。

权重 SHA256：`18895c73e08c814d772435a5b07562c6e380cd9f593b76b14ecf4bf9ba40f1bc`。

原配置 SHA256：`73d756c8fdeaf6095d3d6f7503a6954d451298034d4f5f2f690199c2d312f94a`。

195,608个参数；标签顺序严格保持 **A,F,L,N,R,S,V,|**。波形输入 `[2,205]`：256 Hz、R峰位于索引77，分别为有效点标准化波形和有效掩码。RR输入8维，按选定 config.json 的均值、标准差处理并裁剪到[-8,8]。

原始500 Hz记录先做0.5–40 Hz三阶带通、50 Hz陷波，再重采样到256 Hz。R峰自动定位，心拍边界参考前后相邻R峰中点。RR使用下一心拍，因此不是零延迟分类。

部署按24秒滚动窗口预处理，要求心拍后至少2秒数据，并保留下一RR。正常稳态约2–3秒后回填；还需加排队、预处理和约0.15秒推理。首次启动包含 Python、PYNQ、SciPy 导入，等待时间更长。

滚动窗口的零相位滤波近似训练使用的整段滤波，不能声称两者所有样点完全相同。桌面流式测试得到48个可输出心拍，分类与对应整段参考48/48一致；这只是这两段记录上的验证。

## 板上实测结果

证据：`report/inference_20261104/fpga_replay_results.json`、`fpga_verify.log`、运行状态快照与服务文件。

| 检查项 | 实测 |
|---|---:|
| 真实记录中可用心拍 | 49 |
| FPGA与PyTorch分类一致 | 49/49 |
| 最大logit绝对误差 | 0.000002384185791 |
| FPGA卷积调用数 | 588（每拍12次） |
| 每拍完整推理平均耗时 | 143.61 ms |
| 每拍完整推理最大耗时 | 161.11 ms |
| 纯ARM基线平均耗时 | 182.74 ms（前三拍） |
| 前三拍完整推理速度比 | 约1.25倍 |
| 单拍卷积加速器调用累计耗时 | 约74–75 ms，含轮询及输出同步 |
| 回放显示更新率 | 约28.6–29.7帧/秒；不是本次实测显示器扫描率 |
| 通道1/2运行状态 | 均产生FPGA推理结果，worker存活、无推理错误 |

速度比是同一板卡、同一权重、同样ARM后处理的前三拍对比，基线为单线程NumPy，不能扩展成对所有框架或所有输入的性能结论。当前FP32版本主要完成真实硬件部署，仍有ARM数组搬运、归一化和控制开销。

全记录输出分布为45个N、2个`|`、1个A、1个S。非N输出集中在CN4记录的明显扰动附近；这些输出没有专家标注支持，不能据此判断心律或健康情况。自动R峰检测也可能把扰动当作心拍。

此前优选区间：CN2 4.5–14.5秒、CN4 2–12秒。21个心拍的205点波形窗口落在这些区间内，其板上结果单独保存为 `selected_segment_fpga_results.csv`，全部与PyTorch参考一致。RR及预处理仍使用原连续记录上下文，不是把裁剪片段当作独立记录重新推理。

**49/49 是部署数值一致性，不是临床分类准确率。**

## 固件与时序

- 新固件：`board/inference/overlay/ecg_inference.bit`、同名`.hwh`。
- 控制ABI：`0x45434733`；卷积IP地址`0x40020000`，显示/SPI地址`0x40010000`。
- 100 MHz处理时钟；640×480视频逻辑保持原实现。标签与波形双缓冲，在垂直消隐同时提交。
- 最终实现：WNS **+0.005 ns**、WHS **+0.017 ns**，无失败时序端点。余量较小，后续修改需重新实现和检查。
- LUT **15,606 / 53,200**，FF **20,465 / 106,400**，BRAM Tile **58 / 140**，DSP **57 / 220**。
- 布局布线后执行物理优化修复旧滤波核路径的轻微时序偏差。报告在`board/inference/overlay/`；CDC报告列出的7个跨时钟端点均标为safe。
- RTL仿真通过：SPI、FIFO、按钮、ABI、标签地址范围、待提交缓冲写保护、标签像素渲染及垂直消隐换帧。

## 板卡当前状态及切换

安装目录：`/home/xilinx/jupyter_notebooks/ecg_inference_20261104`。

`ecg-scope.service` 已启用，自启动参数为 **replay、通道2、30 FPS目标**。它回放先前真实ECG，无需ADS1292、网线或串口。实际HDMI输出是否显示正确仍待接回采集卡确认。

最终连续运行检查：同一PID 2232已运行618秒，更新率28.56 FPS，通道2推理进程存活、error=null。此前通道1切换检查也得到19个推理结果；两通道快照分别在`channel1_runtime.json`与`latest_runtime.json`。这是运行状态验证，不是现场观察HDMI。

接好ADS1292后，在Jupyter终端执行以下命令切换成实时采集识别（CN2选2，CN4选1）：

```sh
systemctl stop ecg-scope.service
cd /home/xilinx/jupyter_notebooks/ecg_inference_20261104
/usr/local/share/pynq-venv/bin/python3 install.py --source adc --channel 2
systemctl restart ecg-scope.service
```

切回文件回放：同样执行，把`adc`改为`replay`。不会自动把无ADC的实时模式伪装成当前人体数据。

状态：`/run/ecg-scope/status.json` 和 `/run/ecg-scope/inference_status.json`。新服务首次检查时的NRestarts=31来自此前未接ADS1292导致的旧服务重试，不应记作新回放服务的失败次数；新服务PID保持2232运行。

原服务保存在新安装目录的`ecg-scope.service.original`。旧比特流仍在`ecg_scope_chinese_20261103/board/scope/`，没有覆盖。回退：停止服务，把original文件复制回`/etc/systemd/system/ecg-scope.service`，执行`systemctl daemon-reload`和`systemctl restart ecg-scope.service`。

## 本机交付位置

- 可上传部署包：`board/ecg_inference_20261104.zip`（SHA256：`5598b606e6601a1c43f0687ba4f0be3af45516b25206c16c04bc995d74e98428`）。
- 板上测试笔记本：`ECG_FPGA_Model_Deployment_20261104.ipynb`。
- 逐拍CSV、优选区间CSV、可视化：`模型训练/采集/2026-11-04_真实心电_已保存记录/04_FPGA识别测试/`。
- 完整硬件日志及服务快照：`report/inference_20261104/`。
- 部署说明：`board/inference/GUIDE.md`。
- 源码：`src/hls/ecg_conv.cpp`、`board/inference/`、`src/rtl/ecg_io_top.sv`、`src/rtl/ecg_wave_video.sv`。

仍需现场验证：接采集卡确认新标签画面、按键和视觉对齐；接ADS1292验证实时人体流推理；新模式断电自启动验证。本次没有在用户缺少现场连接的情况下宣称这些测试通过。

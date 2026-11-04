# FPGA 卷积与延后识别

当前监测版为ECG5（0x45434735）：增加中文心率、信号质量和预警状态行，冻结波形时状态行继续更新。

2026-11-04平滑滚动修复：ECG4接口为每个标签列保存字形内部像素位置，允许按1像素移动。标签和波形继续一起在垂直消隐换帧；不再对齐16像素文字格。软件和比特流必须成套使用。

FPGA 执行全部 12 个 FP32 卷积层；ARM 执行 R 峰定位、RR 特征、GroupNorm、门控、全连接及控制。保持 experiment_09/six_db_seed0 权重与 A,F,L,N,R,S,V,| 标签顺序。

实时滚动波形显示 4 秒窗口。识别使用下一心拍 RR 和至少 2 秒后续数据，结果返回后回填在对应心拍上方。问号表示等待。实际总延迟还包括排队与板上推理时间。

`--source replay` 回放此前保存的真实人体 ECG，画面右上角固定显示 **REPLAY**。通道1和2分别来自 CN4、CN2 两次不同采集，不是同步双导联。每轮回放结束清空历史并重新预热。`--source adc` 才使用当下 ADS1292 数据。

先停止服务，再验证：
```
systemctl stop ecg-scope.service
cd /home/xilinx/jupyter_notebooks/ecg_monitor_20261104
/usr/local/share/pynq-venv/bin/python3 verify_fpga.py --output fpga_replay_results.json
```

配置自启动回放或实时采集（将 replay 换成 adc）：
```
/usr/local/share/pynq-venv/bin/python3 install.py --source replay --channel 2
systemctl restart ecg-scope.service
```

BTN0/BTN1 切通道，BTN2 切保真/快速显示路径，BTN3 冻结/恢复。模型独立使用训练预处理，不因显示滤波路径改变而改变。

状态：`/run/ecg-scope/status.json` 与 `inference_status.json`。原服务备份 `ecg-scope.service.original`，恢复时停止服务，将该文件复制回 `/etc/systemd/system/ecg-scope.service`，执行 daemon-reload、restart。

心率以最近最多5个有效RR的中位数为基础平滑显示；质量差、无有效心拍、分析延迟或故障时显示“--”。质量使用平直/削顶/强工频/高频噪声/大幅基线扰动等工程规则，并非ADS1292硬件导联脱落检测，也不能排除所有运动伪迹。

`monitor_config.json`保存演示预警参数：心率低于50或高于120持续10秒才提示，恢复范围内持续5秒解除；连续3个质量合格、概率≥0.90的非N分类才给出“连续非N分类”提示。`|`、低置信度、孤立非N和质量差不会累计分类预警。配置是作品演示规则，不是经临床验证的诊断界限。

监测记录追加到`/var/log/ecg-scope/monitor.jsonl`，含进程、通道、样本计数、心率、质量与状态转换。集成测试的一次性采集由安装目录的`capture_request.json`明确请求，示例`{"seconds":180}`；启动时消耗该请求，保存双路原始`validation_live.npy`及元信息，不会默认持续录制。

数值一致性测试验证部署实现；这些自行采集数据没有专家标注，不能据此计算识别准确率或判断健康状况。有限窗口零相位预处理近似训练的整段滤波，两者存在边缘差异。训练标签 `|` 的含义以训练数据定义为准，不应解释为一种心律类别。

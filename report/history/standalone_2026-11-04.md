# CN2验证与独立展示（2026-11-04）

## CN2真实输入

用户将同一根三电极线从CN4移到CN2。使用外部输入、RLD_SENS=0x2C反馈CH2，默认显示通道2。25.0017秒采集11890样本/通道，预热543点，overruns=0、bad_frames=0、无削顶，实际更新29.9868次/秒。CH2原始交流RMS 0.21725 mV，P1～P99跨度1.27496 mV，49～51Hz占0.5～150Hz能量39.43%。真实HLS保真／快速输出最后4秒图中均有清晰重复尖峰，约1 mV。CH1未接电极，工频占比99.02%，不是有效心电。

板端证据：`ecg_scope_chinese_20261103/board/scope/electrode_cn2_20261104/` 的 raw.npy、filtered_last4s.npy、filtered_last4s.png、quality.json、run_summary.json。此前CN4已有独立验证；这支持两路可分别使用，不等同于同时多导联方案验证。

## 新版运行程序

`board/run_scope_standalone.py` 从已验证中文脚本生成；保持现有中文比特流、双缓冲和滤波数据通路。新增启动通道选项 `--input-channel 1/2`，外部采集时RLD反馈跟随BTN0/BTN1。切换时停止连续读、修改并读回校验06h寄存器、清FIFO后恢复采集，清除旧滤波历史并预热543点。加入单进程文件锁、SIGTERM正常停止、每秒RAM状态文件。

本地主机测试6项通过（显示协议3项、RLD切换3项），涵盖命令顺序、读回失败不恢复采集、无效通道不访问硬件。板上15秒新版测试6887样本/通道、无错误、无溢出或坏帧，29.9785次/秒。

部署小包 `board/ecg_standalone_20261104.zip` 8798字节，SHA256 `298ddadf5e2b2271a923684012d5d2ae4f75e1a1a1079e98c899b49e112d7b99`，整包及内部manifest哈希板上通过。板端目录 `/home/xilinx/jupyter_notebooks/ecg_standalone_20261104`。中文原始发布包未改。

## 系统服务

`ecg-scope.service` 已安装并enabled，由 `/usr/local/share/pynq-venv/bin/python3` 运行，默认CN2、保真、实时，30次/秒。启动顺序在bootpy和PL状态清理服务之后，无network-online依赖。异常10秒重试，不用演示数据替代失败的真实采集。`/run/ecg-scope/status.json` 为RAM运行状态，停止时写 `/var/log/ecg-scope/last_run.json`。首次后台加载约19秒才进入ADC初始化完成；初始20秒检查超时，随后确认服务正常，并非采集崩溃。

首次服务状态：PID26442，active/running，enabled，NRestarts=0；运行76秒时37563样本/通道，2221次更新，29.9913次/秒，无溢出或坏帧，rld_channel=2，warmup_remaining=0。

单进程保护通过：重复启动在加载Overlay前报“already running”，原服务保持运行。通过UI寄存器分别选择CH1、CH2，状态确认RLD反馈随之切换、预热清零、无溢出或坏帧；日志记录06h读回校验，测试存于板端 `ecg_standalone_20261104/channel_transition_test.json`。用户另现场按BTN0→BTN1后确认“恢复正常，通道2心跳清楚”。

已保存pre_reboot.json并安排系统重启。用户随后明确反馈自行重启测试，可以正常运行；未明确说明是否同时拔掉网线，因此不将“无网线冷启动”记为已经现场验证。

导出数据时已确认新boot ID为 `94fd8574-365d-4523-970f-082fed487b0d`（部署前为 `f46cee00-ffc0-4324-839b-7ab9fb2e5a12`）。服务PID854，active/running、enabled、NRestarts=0，启动后持续采集超过900秒，450046样本/通道，无溢出、无坏帧。读取时ui_state=4，用户已切到CH1并冻结，不能将此时累计22.09次/秒的显示统计解读为持续LIVE刷新能力下降。无需运行Notebook采集即可恢复自启动，已得到新boot ID与用户画面反馈双重验证。板卡系统时间错误，所有报告日期以客户端为准。

使用和恢复操作见 `board/STANDALONE_GUIDE.md`。运行服务期间不要直接执行旧Notebook加载Overlay；旧脚本无新版进程锁，调试前应先停止服务。

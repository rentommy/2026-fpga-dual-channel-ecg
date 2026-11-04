# FPGA 双通道心电监测与辅助识别

2026 全国大学生嵌入式芯片与系统设计竞赛，AMD 自主选题赛道初级组。器件：AMD XC7Z020CLG400-1，平台：PYNQ-Z2。团队：任家霖、程硕、李一博。项目原创代码采用 MIT，第三方材料见 [依赖说明](docs/third_party.md)。

本仓库按竞赛提交目录整理，包含完整代码、技术文档、海报和硬件设计；工作站原始资料与大体积生成工程保留本地。上传前阅读 [提交核查清单](report/submission_checklist.md)。仍有未完成项，不能将本目录描述为已完成全部比赛验收。

## 功能与分工

自主设计ADS1292采集板经隔离SPI传输两个输入通道的24位数据，配置采样率500Hz。PL完成双路径滤波、50Hz陷波和12层FP32卷积，ARM完成R峰、RR、心率、归一化/分类与控制，HDMI显示滚动波形、中文状态和延时回填标签。模型使用后续心拍信息，分类标签通常延后约2–3秒出现。

SW0=0为单路，启动默认低延迟实时路径；SW0=1为当前选中输入的上下双路径，上实时、下保真，两栏共用增益、保留滤波时间差。BTN0/BTN1选通道1/2，BTN2切单路模式，BTN3冻结/恢复。双路模式固定显示两条路径，BTN2不改变上下布局。

30ms/348ms是滤波核既有脉冲峰值偏移，不是整机端到端延迟。两输入通道分别完成电极测试，尚不能据此声称同步双导联人体实验通过。心率、质量门控和提示是工程演示，系统不用于临床诊断。

## 实测证据

| 项目 | 结果与边界 |
|---|---|
| FPGA与PyTorch部署一致性 | 49/49记录心拍分类一致，最大logit误差2.384e-6；不是临床准确率 |
| 完整推理 | 后续测试平均约120ms/拍；前三拍与单线程NumPy基线约1.51倍，仅限该测量 |
| 当前显示固件 | WNS +0.016ns、WHS +0.002ns，失败端点0；LUT15735、FF20490、BRAM60、DSP57 |
| 现场界面 | 用户确认中文、按键、标签平滑与SW0上下分屏；增益修复后的最终实际波形仍待用户确认 |
| 电源恢复复查 | 同一PID采样计数持续增加，约27帧/秒，无丢帧/坏帧，质量恢复GOOD；固定供电后的复查窗口约30秒，不能当成长时稳定测试 |

详细材料：[当前设计报告](report/design_report.md)、[历史记录](report/history/)、[实测汇总证据](report/evidence/)、[大模型协作记录](report/llm_log/README.md)。历史文档可能包含已被纠正的旧结论，以当前报告和对应版本的原始证据为准。

## 目录对照

| 目录 | 作用 |
|---|---|
| `src/hls/`、`src/rtl/`、`src/ps/` | 滤波/卷积源码、采集/视频RTL、浮点参考 |
| `sim/` | 合成向量生成、C/RTL验证入口与主机检查 |
| `build/` | 从源代码构建入口和本次实现报告；生成工程不入库 |
| `board/runtime/` | 当前配套Python、模型导出、bit/hwh、服务安装 |
| `board/` | 从空工程创建Zynq/视频/卷积设计及管脚约束 |
| `data/` | 合成测试输入、参考输出；人体原始记录不公开 |
| `model/` | 原始选定权重、配置与训练来源快照 |
| `skill/` | 可复用报告门控、Overlay ABI校验及缓存排查经验 |
| `report/` | 当前报告、提交清单、实测证据、历史记录与协作记录 |
| `docs/` | 复现、依赖、硬件接口及已知限制 |

## 主机侧复现

Python 3.11/3.12，安装 `python -m pip install -r requirements.txt`。

```text
python sim/make_synthetic_data.py
python sim/gen_vectors.py
python sim/make_model_vectors.py
python sim/run_host_tests.py
g++ -std=c++11 -O2 -I src/hls src/hls/ecg_filter.cpp src/hls/tb_ecg_filter.cpp -o build/filter_test
./build/filter_test
g++ -std=c++11 -O2 -I src/hls src/hls/ecg_filter.cpp src/hls/ecg_filter_top.cpp src/hls/tb_ecg_filter_top.cpp -o build/filter_top_test
./build/filter_top_test
```

测试输入均为合成数据。旧报告中的实测滤波误差、49拍分类对照来自不同数据，不能用这里的新合成结果冒充原实验复现。

## PYNQ直接运行

将本仓库复制到板卡，依赖现有PYNQ环境、NumPy/SciPy/Pillow。首次硬件接线见 [硬件说明](docs/hardware.md)。选定模型的权重和配置已经包含。

```text
sudo systemctl stop ecg-scope.service
cd board/runtime
sudo /usr/local/share/pynq-venv/bin/python3 install.py --source adc --channel 2
sudo systemctl start ecg-scope.service
```

本交付bit/hwh来自2026-11-04完整干净重建，ABI为ECG6；新构建产物尚未重新上板。软件兼容预编译层级`ecg_io_dual`与全新构建层级`ecg_io`。采集板上CN2对应通道2、CN4对应通道1。该命令会安装自启动服务；只在本人板卡、硬件准备完毕时执行。原始人体数据不自动持续录制。

## 从源代码构建

Vivado/Vitis 2026.1，PYNQ-Z2。Windows在AMD工具命令环境运行：

```text
powershell -File build/build_all.ps1
```

入口先解压配套第三方依赖，再导出两个HLS IP，随后从空工程生成完整系统。若已有`build/vivado/ecg_scope`，需使用新的干净检出目录，脚本不会自行删除旧工程。详细步骤、环境和验证边界见 [复现说明](docs/reproduce.md)。2026-11-04已完成独立空目录HLS至bit完整重建，时序通过；见 [重建报告](report/full_clean_build_2026-11-04.md)。新生成bit尚未重新上板验收。

## 全部代码归档

本目录同时包含当前运行源码和archive/original_code下的历史/训练/STM32源文件。原路径见archive/source_map.json。指定的第三方学习复现项目已排除，人体原始数据保留本地；无需压缩生成工程。完整重建证据见report/full_clean_build_2026-11-04.md。

## 技术文档与海报

- [技术文档](docs/technical_report_zh.docx)
- [English poster](docs/posters/amd_poster_en.pptx)
- [中文海报](docs/posters/amd_poster_zh.pptx)
- [作品全貌](docs/images/prototype_overview.jpg)
- [硬件图纸与PCB](hardware/README.md)

文件夹和文件名统一为英文，中文正文保留。其他归档路径与原始文件名的对应关系见archive/source_map.json、hardware/file_origin.json和docs/publication_file_map.json。

The external learning/reproduction project `ECG-with-Deep-learning-master` is intentionally excluded. Personal raw ECG recordings, captures, datasets, virtual environments, credentials and generated work directories remain local. Public signal fixtures are synthetic. Historical records describe the versions and conditions under which their results were obtained.

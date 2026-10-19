# 双通道心电监测系统 —— FPGA 多通道双延迟生物电滤波核

2026 嵌入式芯片与系统设计竞赛 · FPGA 创新设计赛道 · AMD 自主选题（初级组）

**组员**：任家霖　程硕　李一博

---

## 这个系统是什么

ADS1292 采集双导联心电 → PYNQ-Z2 上的 FPGA 实时滤波 → PS 侧显示、心率/ST 测量与模型判读。

滤波核的特点是**每通道并行两条不同延迟的通路**，由同一份采样数据产生：

| 通路 | 延迟 | 服务于 |
|---|---|---|
| 低延迟通路 | 30 ms | 实时波形显示、报警，以及肌电一类闭环场景 |
| 诊断通路 | 348 ms | ST 段测量、波形存档、模型推理 |

两条通路共享前级，增量成本是**一个 DSP48 的 0.084%**，而低延迟通路的延迟
**不因为诊断通路的存在而增加一个时钟**。详见 `report/why_fpga.md`。

滤波核本身与心电无关，是通用的多通道生物电前端；通道数与每通道的延迟
都是配置参数，片上 BRAM 可支撑约 520 条双通路。

---

## 硬件

| 部件 | 说明 |
|---|---|
| PYNQ-Z2 (XC7Z020) | 滤波核 + PS 侧应用 |
| ADS1292R 采集板 | 双导联，24 bit，500 SPS，**电池供电** |
| ISO7763DWR 数字隔离器 | 采集板与 PYNQ-Z2 之间的 SPI 隔离 |

---

## 目录结构

竞赛要求提交物使用纯英文路径（选题指南 §3.3.5.4），本仓库全部目录与文件名为英文，
中文仅出现在文件内容与注释中。

| 目录 | 内容 |
|---|---|
| `src/hls/` | HLS 源码：接口契约 `ecg_filter.h`、实现 `ecg_filter.cpp`、测试平台 `tb_ecg_filter.cpp`、规格书 `INTERFACE.md`、自动生成的系数头 `ecg_filter_coef.h` |
| `src/ps/` | PS 侧 Python：`hw_filter_ref.py` 是滤波链的浮点黄金参考（全项目的"标准答案"） |
| `src/rtl/` | 手写 RTL（预留） |
| `sim/` | 仿真与参数决策脚本：`gen_vectors.py` 生成系数头与测试向量，其余为参数扫描与评价 |
| `sim/experiments/` | 定稿滤波效果图：`plot_boxcar.py` 与它产出的六栏图 |
| `old/` | **否证记录** —— 被实测推翻或被更好结构取代的旧方案，按五类归档，18 个脚本全部仍可运行。每类被什么取代见 `old/README.md` |
| `data/` | 测试向量。`source/` 是实测原始采集，其余由 `gen_vectors.py` 生成 |
| `model/` | 心拍分类模型：`ecg_model.onnx` 权重，`ecg_model_classes.txt` 类别名 |
| `board/` | 上板运行脚本与实测日志 |
| `report/` | 设计报告 `design_phase1.md`（阶段一，部分结论已被推翻）与 `design_phase2.md`（**阶段二，现行定稿**）、创新点 `innovation.md`、`why_fpga.md`、`llm_log/` 大模型协作记录 |
| `skill/` | 通用 PYNQ 技能包 |
| `build/` | 编译产物，不入库 |

---

## 快速复现

### 1. 生成系数与测试向量

```bash
python sim/gen_vectors.py
```

产出 `src/hls/ecg_filter_coef.h`（定点系数与全部参数）和 `data/` 下的六个向量文件。

### 2. 跑 C 仿真（不需要 Vitis）

```bash
mkdir -p build
g++ -std=c++11 -O2 -I src/hls \
    src/hls/ecg_filter.cpp src/hls/tb_ecg_filter.cpp -o build/tb_ecg_filter
./build/tb_ecg_filter
```

退出码 0 表示五项检查全过：黄金参考比对、冲激响应、50 Hz 抑制、
位宽声明核对、两条通路的延迟核对。

当前实测：定点与浮点参考的最大偏差 **3.3 码（0.158 µV）**，RMS 0.698 码。

顶层（含 AXI 接口与约束）也能用 g++ 验：

```bash
g++ -std=c++11 -O2 -I src/hls src/hls/ecg_filter.cpp \
    src/hls/ecg_filter_top.cpp src/hls/tb_ecg_filter_top.cpp -o build/tb_top
./build/tb_top
```

检查黄金比对、通道间无串扰、逐通道延迟配置是否生效。

### 3. Vitis HLS 综合（需要工具链）

```bash
vitis_hls -f src/hls/run_hls.tcl                  # C 仿真 + 综合
vitis_hls -f src/hls/run_hls.tcl -tclargs export  # 再导出 IP
vitis_hls -f src/hls/run_hls.tcl -tclargs all     # 再加 C/RTL 协同仿真

python sim/collect_hls_report.py --samples 2000   # 报告提成 Markdown 表
```

器件 `xc7z020clg400-1`，100 MHz。约束与预期数字见 `src/hls/INTERFACE.md` §7。
`collect_hls_report.py` 与课题无关，任何 HLS 工程都能用，
带 `--selftest` 可在没有工具链的机器上验证解析逻辑。

### 4. 复现滤波效果图

```bash
python sim/experiments/plot_boxcar.py
```

产出 `sim/experiments/boxcar_L320_D159.png`：基线估计、输出波形、残留漂移、
平均心拍、逐拍 ST60 与 T 峰误差分布，共六栏。

### 5. 重跑参数决策

```bash
python sim/measure_wander.py                  # 输入信号的实测干扰量级：漂移峰峰值、50 Hz 幅度
python old/dc_block_v1/evaluate_chains.py     # 旧定稿的候选链对比（结论已被取代）
```

`measure_wander.py` 的 §① ② ③ 量的是**输入信号**有多脏，与滤波器选型无关，仍然有效；
§④ 是旧直流阻断的级数选择，已被矩形窗取代。`evaluate_chains.py` 的候选集全是旧的移位链，
留作决策过程的记录 —— 为什么被取代见 `old/README.md`。

---

## 当前状态

- [x] 滤波链结构与参数定稿，依据见 **`report/design_phase2.md`** 与 `report/llm_log/`
      （`design_phase1.md` 是阶段一的旧链路，开头有对照说明）
- [x] 接口契约、定点实现、C 仿真测试平台，五项检查全过
- [x] 双延迟通路架构与资源论证（`report/why_fpga.md`）
- [x] HLS 综合顶层、AXI 接口、综合约束、批处理脚本、报告采集工具
- [ ] 在装有 Vitis 的机器上实际跑一遍综合，核对资源与时序
- [ ] Vivado 工程与 PYNQ overlay
- [ ] PS 侧驱动与上位机
- [ ] 电极脱落检测（EMRMS 包络）—— 当前完全缺失，实测脱落时输出会冲到 270 mV
- [ ] 扩充采集数据：现有标定数据仅两段 60 秒、一个被试

---

## 安全须知

以下每一条都对应一次实际风险，**不是形式条款**。

- **采集板只能用电池供电，测量时不接充电器**；烧完程序立刻拔掉 ST-Link，不能连着测。
- **ADS1292 接人体时绝不能直连市电供电的 PYNQ-Z2** —— 安全问题，且 50 Hz 干扰
  会回到难以滤除的量级。必须经数字隔离器，采集板继续电池供电。
- **电池组装必须从最低那节往上接**（GND → VC1 → VC2 → …）。乱序可能使 VC 脚
  超过 6 V 绝对最大额定值而损坏芯片；GND 与电芯的连线**绝不可断开**。
- **激活按钮绝对不能接 CN1 第 2 脚（P+）** —— 按下会把整组电池短路，可能起火。
- 香橙派 26 pin 全部 3.3 V，与 STM32 直连；中间加 3.3→5 V 转换会打坏 H616。

---

## 免责声明

本系统是**课程与竞赛演示装置，未经任何医疗认证，输出不可用于诊断**。
文档中出现的 ST 段、T 波等临床术语仅用于描述信号处理指标，不构成医学结论。

---

## 许可

见 `LICENSE`。

# ECG 模型改进

此目录独立于原复现项目。第一阶段保持原 SENet-LSTM 结构，解决数据追溯、记录隔离评估和房早逐窗口分析。

## 固定定义

- 原始数据只读引用 `../项目复现/ECG_ren/`，新数组、元数据、划分和实验均写入本目录。
- 输入：目标单导联、10 秒不重叠窗口、重采样 3600 点、保留三位小数，训练时逐窗口 z-score。
- 标签：沿用旧 S→A、F→V 的简化映射，不宣称这是标准 AAMI 五类协议。N 或起搏符号 `/` 组成的窗口保留旧 N 规则，这一规则有语义局限，记录在清单中。其余窗口取映射后最多的异常类别，并列按固定类别顺序决定；无有效标签为 Q。
- 质量：排除原始缺失、重采样后恒定窗口及 Q，不把缺失信号填零作为正常样本训练。
- 划分：固定种子的嵌套分层分组划分，目标约 60%/20%/20%，实际比例取决于记录长度。使用数据库+记录编号作为分组代理，MIT 201/202 保守合并。未确认其他记录之间及跨数据库的受试者身份，因此只称记录隔离基线，不能宣称完成了严格受试者独立验证。
- 模型：复制原 SENet-LSTM 实现，不扩大模型。N 权重预先固定 0.7，其余沿用旧配置。验证 macro-F1 选点，最多 60 轮，早停 10 轮，seed=0。
- 房早原因分析只使用验证集；测试集仅作最终性能核对。单次基线无法证明新结构提升，也不能给出性能上限。

## 运行

PowerShell，在此目录下：

当前独立环境为 Python 3.12、PyTorch 2.7.1 + CUDA 12.8。完整依赖见 `requirements.lock.txt`，CPU 流程检查的环境另存于 `requirements.cpu_preflight.lock.txt`。重新安装依赖时需加入 PyTorch 官方 CUDA 索引：`--extra-index-url https://download.pytorch.org/whl/cu128`。

```powershell
.\.venv\Scripts\python.exe -m unittest test_pipeline.py
.\.venv\Scripts\python.exe pipeline.py prepare
.\.venv\Scripts\python.exe pipeline.py split
.\.venv\Scripts\python.exe pipeline.py coverage
.\.venv\Scripts\python.exe pipeline.py train
.\.venv\Scripts\python.exe summarize_run.py
.\.venv\Scripts\python.exe extra_diagnostics.py runs/record_baseline_seed0
```

数据清单和划分写成后拒绝覆盖，实验目录存在时拒绝覆盖。若需不同规则，请使用独立版本目录，保留旧版。

`runs/cpu_preflight_seed0/` 是七轮 CPU 流程检查，未评估新测试集，不参与最终模型选择。正式运行 `runs/record_baseline_seed0/` 在 GPU 上从固定种子重新开始。

## 结果位置

- `data/manifest.json`：规则、版本、原始数据和旧 CSV 的 SHA256、排除统计。
- `data/windows.csv`：记录、导联、采样率、窗口位置、异常拍数量与位置、质量信息。
- `data/split.csv` 和 `split_summary.json`：初始分组划分与缺类提示。
- `data/split_coverage.csv` 和 `coverage_summary.json`：仅基于标签来源、训练前固定的覆盖修正版。对来源足够的类别补齐三边覆盖，移动最短的可行记录，不读取模型分数。当前移动记录 207 到测试集。B 仅来自记录 36，无法补齐，其验证与测试性能不可估计。训练实际使用此修正版。
- `runs/record_baseline_seed0/`：配置、训练曲线数值、最优权重、分类指标、逐窗口预测。
- `A_validation_strata.csv`：单个/多个 A、边界位置、各记录的召回率。
- `A_validation_errors.csv`：房早漏检逐窗口清单。

更换任务或采样规则后，准确率不可与旧随机窗口划分的 95.19% 直接视为同条件比较。

# 第三轮：MIT-BIH 同导联与真实时宽基准

## 预先固定的实验

只用 MIT-BIH 的 MLII。目标仍保留九类原始符号，不合并标签；单库的 B 无样本，S 来源不足，不能声称完成九类验证。

数据采用每记录独立的三阶 0.5–40 Hz 零相位带通。相邻候选中点限制中心拍范围，只用中心标注作标签。

- `physical`：360 Hz 原时间轴，目标固定在第 108 点，总长 288 点（前 0.3 秒、后 0.5 秒）。周期外补零，额外有效区域 mask。不把周期缩放。
- `warped`：同一周期的左右部分分别插值到 108/180 点，目标同样对齐，作为周期缩放对照。
- 两者使用同一原始中心周期的均值与标准差。没有把补零纳入统计。
- 同时改变了时间支持与 mask 形状，因此是预处理方案对照，不是关于 QRS 时宽的单因素因果证明。

四组小 CNN：上述两种输入分别比较有无独立 RR 分支。另加“降采样形态＋mask＋RR”的加权线性 SVM 成熟分类器基准，不冒称已精确复现某篇论文。

四组验证完成后、读取测试集之前，补充了固定参数 RBF-SVM（C=10、gamma=scale），作为非线性传统分类器对照；未调参，补充原因已记入 protocol.json。

记录与受试者划分固定种子，201/202 合为同一人；仅按标签覆盖作确定性修正，所有修正记录在清单中。极少来源类别仅留训练，不拆散受试者补齐验证。单拍定位来自专家候选，不包含自动检测误差。

四组 CNN 的 seed0 只看验证集，选定一个配置后重复 seed1/2。上述过程结束后才执行 `finalize`，读取 SVM、三次选定配置及其等权概率平均的最终测试成绩。不按测试成绩挑种子或配置。

这一数据库已在以前轮次使用，因此本轮测试只用于本轮冻结协议核对，不是全新外部验证。三个种子也不能替代多个受试者划分。

## 运行

在本目录使用父目录的独立环境：

```powershell
..\.venv\Scripts\python.exe -m unittest -v test_benchmark.py
..\.venv\Scripts\python.exe benchmark.py prepare
..\.venv\Scripts\python.exe benchmark.py svm
..\.venv\Scripts\python.exe benchmark.py svm-rbf
..\.venv\Scripts\python.exe run_validation.py
..\.venv\Scripts\python.exe audit.py
..\.venv\Scripts\python.exe diagnose.py
..\.venv\Scripts\python.exe benchmark.py finalize
```

数据和运行目录拒绝覆盖。SVM 与神经验证可以独立运行，GPU 实验逐个执行。`data/manifest.json` 保存原始文件、处理规则与校验值；每个神经实验保留源码快照。`selection.json` 只依据验证分数生成，`final/` 一次性保存本轮最终评估。

标注依据：[PhysioNet 标准标注](https://physionet.org/static/lightwave/doc/annotations.html)。数据与 201/202 身份依据：[MIT-BIH 数据库](https://physionet.org/content/mitdb/1.0.0/)。伪迹不是生理心拍。

## 结果入口

- `结果报告.md`：冻结配置后的最终评估。
- `验证失败定位.md`：训练与验证的逐类别落差。
- `validation_record_diagnostics.csv`：验证集每条记录、每种类型的识别情况。
- `data/预处理对照.png`：同一原始心拍的两种输入。
- `data/audit.json`、`snapshot_audit.json`：标注、划分、补零与源码一致性核对。

线性 SVM 的两次原始问题求解和一次 dual=True、10000 次上限的运行均未产生模型，保留三个 `runs/svm_*interrupted` 目录及日志。最终使用 dual=True、1000 次迭代上限，C、权重、特征与划分不变，迭代次数和是否触及上限记入配置；若未收敛，仅作有限计算下的参考，报告明确标记。恢复决策发生在读取测试成绩之前，并已记入协议。

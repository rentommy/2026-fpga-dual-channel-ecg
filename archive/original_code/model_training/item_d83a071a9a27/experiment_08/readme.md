# 第八轮：双向带通＋50Hz陷波

按用户图片实现的滤波函数在 `filtering.py`：

```python
sos = signal.butter(3, [0.5, 40.0], btype='bandpass', fs=fs, output='sos')
y = signal.sosfiltfilt(sos, np.asarray(x, dtype=np.float64))
b, a = signal.iirnotch(50.0, 30.0, fs=fs)
y = signal.sosfiltfilt(signal.tf2sos(b, a), y)
```

在每条原始记录的原采样率下执行，再重采样到256Hz和截取单拍。原第七轮已使用双向带通；新增的是50Hz陷波双向处理。未把50Hz作为所有数据库都有的工频干扰假设，而是按指定参数做对照。

与第七轮最终候选保持相同网络、标准化、标签、RR、患者划分、批次大小、损失、学习率、最大轮数与早停规则；分别使用seed0/1/2。比较MIT开发验证，不重复使用外部测试调滤波。旧权重和原始文件不变。

运行顺序（使用上级项目 `.venv/Scripts/python.exe`）：

1. `run.py prepare`：生成新波形数据；已生成的冻结数据拒绝覆盖。
2. `test_filter.py`：核对与图片算法一致，并在128/257/360Hz下验证50Hz抑制及10Hz通带保留。
3. `compare.py verify`：确认除波形数值外，标签、掩码、RR、中心位置、划分等完全相同。
4. `train_notch.py`：三种子训练，重载权重验证预测可复现，生成 `结果报告.md`。

`setup_experiment.py`仅首次生成隔离副本使用，不应对已完成实验重复执行。`normalize_study.py`保留了第七轮的训练函数；本轮入口是`train_notch.py`，不会执行该文件中的扩展选型流程。

注意：50Hz已位于40Hz带通上限之外，因此额外陷波不必然带来明显识别提升；双向滤波仍然依赖未来信号，不是实时因果滤波实现。最终是否采用依据三种子对照结果，当前不自动替换部署权重。

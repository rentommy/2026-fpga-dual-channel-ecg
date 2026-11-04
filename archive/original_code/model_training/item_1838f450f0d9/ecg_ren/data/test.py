import wfdb
import numpy as np
import pandas as pd
import os
from pathlib import Path
from scipy import signal

path = r"D:/桌面/心率作业/项目复现/ECG_ren/"

# ============ 四个数据库的配置 ============
# 换库只需要改 i（0~3），导联名会自动切换
DATABASES = [
    {"folder": "european-st-t-database-1.0.0",          "lead": "MLIII"},  # i=0 欧洲 ST-T，250Hz
    {"folder": "mit-bih-arrhythmia-database-1.0.0",     "lead": "MLII"},   # i=1 MIT-BIH 心律失常，360Hz
    {"folder": "mit-bih-st-change-database-1.0.0",      "lead": "ECG"},    # i=2 MIT-BIH ST 变化，360Hz
    {"folder": "sudden-cardiac-death-holter-database-1.0.0", "lead": "ECG"},  # i=3 猝死库，250Hz
]

i = 0                        # ← 换库改这里（0~3）
db = DATABASES[i]

TARGET_FS = 360              # 统一目标采样率 360Hz
TIME = 10                    # 窗口 10 秒
SEG_LEN = TARGET_FS * TIME   # 3600 点

# ============ 提取记录名（用 .dat 后缀，自动适配不同文件名格式）============
files = os.listdir(path + db["folder"])
name_list = sorted([Path(f).stem for f in files if f.endswith('.dat')])

ecg_data = []      # 收集所有 10 秒段
symbols_data = []  # 收集所有标签

for num in name_list:
    # 一次性读整条记录（快），不再每个窗口读一次
    record = wfdb.rdrecord(path + db["folder"] + '/' + num)
    ann = wfdb.rdann(path + db["folder"] + '/' + num, 'atr')

    fs = record.fs
    if db["lead"] not in record.sig_name:
        print(f"记录 {num} 没有 {db['lead']} 导联，实际：{record.sig_name}，跳过")
        continue

    n = record.sig_name.index(db["lead"])
    full_signal = record.p_signal[:, n]          # 取整条目标导联

    ann_sample = np.asarray(ann.sample)          # 每个 R 波位置（整条记录）
    ann_symbol = np.asarray(ann.symbol)          # 每个心拍类型

    win = fs * TIME                              # 每窗口原始采样点数（250*10=2500 或 360*10=3600）
    k = 0
    while (k + 1) * win <= len(full_signal):
        st = k * win
        en = (k + 1) * win

        # 切片 + 重采样到 3600
        seg = full_signal[st:en]
        seg_fixed = np.round(signal.resample(seg, SEG_LEN), 3)
        ecg_data.append(seg_fixed)

        # 这个窗口内的标注
        mask = (ann_sample >= st) & (ann_sample < en)
        symbols = list(ann_symbol[mask])

        # 打标签
        if len(symbols) == 0:
            symbols_data.append('Q')
        elif symbols.count('N') / len(symbols) == 1 or symbols.count('N') + symbols.count('/') == len(symbols):
            symbols_data.append('N')
        else:
            non_N = [s for s in symbols if s != 'N']
            most = max(set(non_N), key=non_N.count)   # 出现最多的非 N 标签
            symbols_data.append(most)

        k += 1

# ============ 保存 ============
pd.DataFrame(ecg_data).to_csv(f'{db["lead"]}_ecg_data.csv', index=False)
pd.DataFrame(symbols_data).to_csv(f'{db["lead"]}_symbols_data.csv', index=False)
print(f"完成：共 {len(ecg_data)} 段，已保存 {db['lead']}_ecg_data.csv 和 {db['lead']}_symbols_data.csv")

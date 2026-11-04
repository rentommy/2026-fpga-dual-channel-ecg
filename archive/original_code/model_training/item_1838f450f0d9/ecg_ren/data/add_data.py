import wfdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
from pathlib import Path
import scipy
from scipy import signal
from tqdm import tqdm

path = r"D:/桌面/心率作业/项目复现/ECG_ren/"                            #设置路径
datas = ["european-st-t-database-1.0.0",
    "mit-bih-arrhythmia-database-1.0.0",
    "mit-bih-st-change-database-1.0.0",
    "sudden-cardiac-death-holter-database-1.0.0"]
leads = ["MLIII", "MLII", "ECG", "ECG"]   # 每个数据库对应的导联名
i=3

# 用 RECORDS 文件拿到官方记录列表（避开 102-0 这类不完整文件）
with open(path + datas[i] + '/RECORDS', 'r', encoding='utf-8') as f:
    all_names = [line.strip() for line in f if line.strip()]

# 只保留有 .atr 标注文件的记录（猝死库等不是所有记录都有标注）
name_list = [n for n in all_names if os.path.exists(path + datas[i] + '/' + n + '.atr')]

ecg_data = []                                                            # 收集输出结果
symbols_data = []

# 心拍类型 → AAMI 7类 映射（排除 ~ + s T 等非心拍标记）
AAMI_MAP = {'N': 'N', 'L': 'L', 'R': 'R', 'V': 'V', 'A': 'A', '|': '|', 'B': 'B',
            'S': 'A',   # 室上性早搏 → 房性(A)
            'F': 'V'}   # 融合心搏 → 室性(V)，简化处理
BEAT_TYPES = set(AAMI_MAP.keys())

for num in tqdm(name_list, desc="处理记录"):                              # 遍历文件号，带进度条
    #num = "e0103"
    header = wfdb.rdheader(path + datas[i] + '/' + num)                   # 读取头文件
    fs = header.fs                                                        # 读取采样率
    total = header.sig_len                                                # 读取总采样数

    record = wfdb.rdrecord(path + datas[i] + '/' + num) # 读取10秒窗口内的 ECG 信号数据
    ann = wfdb.rdann(path + datas[i] + '/' + num, 'atr') 

    k = 0
    time = 10                                                             #设置10秒窗口
    while k * fs * time + fs * time <= total:
        st = k * fs * time
        en = k * fs * time + fs * time
        
        if leads[i] in record.sig_name:                                   # 找目标导联
            n = record.sig_name.index(leads[i])                                                              

            #print(n)
            #print(record.sig_name)
            #print(record.n_sig)
            ecg_ = record.p_signal.transpose()                            # 交换坐标轴
            ecg = ecg_[n,st:en]                                           # 按窗口切片
            #print(ecg)
            re_signal = scipy.signal.resample(ecg, 3600)                  # 取MLIII导联的心电数据,重采样
            re_signal = np.nan_to_num(re_signal)                          # NaN→0（猝死库有空洞）
            re_signal_3 = np.round(re_signal, 3)                          # 保留小数
            ecg_data.append(re_signal_3)                                  # 保存10秒数据段


            ann_sample = np.asarray(ann.sample)
            ann_symbol = np.asarray(ann.symbol)
            mask = (ann_sample >= st) & (ann_sample < en)
            symbols = list(ann_symbol[mask])
            #symbols=ann.symbol
            if len(symbols) == 0:
                symbols_data.append('Q')
            elif symbols.count('N') / len(symbols) == 1 or symbols.count('N') + symbols.count('/') == len(symbols):  # 如果全是'N'或'/'和'N'的组合，就标记为N
                symbols_data.append('N')
            else:
                beats = [s for s in symbols if s in BEAT_TYPES]         # 只留心拍，排除 ~ + s T 等标记
                if len(beats) == 0:
                    symbols_data.append('Q')                            # 没有有效心拍标注
                else:
                    non_N = [AAMI_MAP[s] for s in beats if s != 'N']    # 映射到 AAMI 并排除 N
                    if len(non_N) == 0:
                        symbols_data.append('N')                        # 只有 N
                    else:
                        most = max(set(non_N), key=non_N.count)         # 出现最多的异常心拍
                        symbols_data.append(most)

            # print(label)
        k+=1
ecg_data=pd.DataFrame(ecg_data)
symbols_data=pd.DataFrame(symbols_data)
out = os.path.dirname(os.path.abspath(__file__))   # 脚本所在目录
ecg_data.to_csv(out + f'/{i}{leads[i]}ecg_data.csv', index=False)
symbols_data.to_csv(out + f'/{i}{leads[i]}symbols_data.csv', index=False)
print("csv文件生成完成")
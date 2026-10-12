# -*- coding: utf-8 -*-
"""
硬件滤波链的浮点参考实现（黄金参考）

这个文件是整个项目的"标准答案"：HLS 写的定点版本、上板跑出来的结果，
都要和这里的输出逐点比对。

三级结构，按"硬件代价从小到大"排：
  ① 直流阻断   —— 移位实现，零乘法器
  ② 50Hz 陷波  —— 二阶 biquad，5 个乘法器
  ③ 低通       —— 对称 FIR，折叠后 ceil(N/2) 个乘法器
"""
import numpy as np
from scipy import signal

FS = 500                    # ADS1292 采样率
LSB_UV = 48.081e-3          # 1 个 ADC 码 = 48.081 nV = 48.081e-3 µV









# ══════════════════════════════════════════════════════════════════
#  ① 直流阻断：用移位代替乘法
# ══════════════════════════════════════════════════════════════════
def dc_block_shift(x, k):
    """
    一阶高通
    截止频率 fc = fs / (2π · 2^k)
        k=7  → 0.622 Hz
        k=8  → 0.311 Hz
        k=9  → 0.155 Hz
    """
    step = 1.0 / (1 << k)                   #设置滤波参数
    acc = 0.0                               #初始化滤波参数
    y = np.empty(len(x), dtype=np.float64)  #生成64位浮点数组
    for n in range(len(x)):                 #高通滤波
        acc += (x[n] - acc) * step
        y[n] = x[n] - acc
    return y


def dc_block_fc(k, fs=FS):                  #计算截止频率
    return fs / (2.0 * np.pi * (1 << k))


def dc_block_cascade(x, k, stages):         #多级直流阻断
    """
    直流阻断级联 stages 级
    """
    y = np.asarray(x, dtype=np.float64)
    for _ in range(stages):
        y = dc_block_shift(y, k)
    return y








# ══════════════════════════════════════════════════════════════════
#  ② 50Hz 陷波：二阶 biquad
# ══════════════════════════════════════════════════════════════════
def notch_coef(f0=50.0, Q=30.0, fs=FS):
    """
    计算 (b, a)，二阶 IIR 陷波器系数
    带宽 = f0 / Q。
    """
    return signal.iirnotch(f0, Q, fs=fs)


def notch_apply(x, b, a):
    """
    二阶 IIR 陷波器
    y[n] = b0·x[n] + b1·x[n-1] + b2·x[n-2] - a1·y[n-1] - a2·y[n-2]
    """
    return signal.lfilter(b, a, x)








# ══════════════════════════════════════════════════════════════════
#  ③ 低通：对称 FIR
# ══════════════════════════════════════════════════════════════════
def fir_lowpass(n_taps, fc=40.0, fs=FS, window='hamming'):         #使用对称汉明窗
    """
    计算冲激响应系数
    对称线性相位 FIR 低通。
    固定群延迟 (N-1)/2 个采样点
    """
    assert n_taps % 2 == 1, 'n_taps 需取奇数，使群延迟为整数'        #检查冲激响应系数数量
    return signal.firwin(n_taps, fc, fs=fs, window=window)


def fir_apply(x, h):      
    """
    低通滤波
    """                                          #FIR滤波器
    return signal.lfilter(h, [1.0], x)


def fir_group_delay(n_taps):                                        #计算FIR滤波器群延迟
    """
    对称 FIR 的群延迟，单位：采样点
    """
    return (n_taps - 1) // 2








# ══════════════════════════════════════════════════════════════════
#  完整硬件滤波链路
# ══════════════════════════════════════════════════════════════════
def chain_hw(x, k=7, notch_q=30.0, n_taps=31, fs=FS):
    y = dc_block_shift(np.asarray(x, dtype=np.float64), k)
    b, a = notch_coef(50.0, notch_q, fs)  
    y = notch_apply(y, b, a)
    h = fir_lowpass(n_taps, 40.0, fs)
    y = fir_apply(y, h)
    return y









# ══════════════════════════════════════════════════════════════════
#  原来上位机的链路，两个版本，用来做对照
# ══════════════════════════════════════════════════════════════════
def chain_orig_zerophase(x, fs=FS):
    """
    原版香橙派：巴特沃斯带通 + 陷波
    sosfiltfilt 双向滤波零相移
    """
    x = np.asarray(x, dtype=np.float64)
    sos = signal.butter(3, [0.5, 40.0], btype='bandpass', fs=fs, output='sos')  #计算滤波系数
    y = signal.sosfiltfilt(sos, x)                                              #双向滤波
    b, a = signal.iirnotch(50.0, 30.0, fs=fs)                                   #计算陷波系数
    return signal.sosfiltfilt(signal.tf2sos(b, a), y)                           #双向滤波


def chain_orig_causal(x, fs=FS):
    """
    原版香橙派单向 sosfilt
    """
    x = np.asarray(x, dtype=np.float64)
    sos = signal.butter(3, [0.5, 40.0], btype='bandpass', fs=fs, output='sos')
    y = signal.sosfilt(sos, x)
    b, a = signal.iirnotch(50.0, 30.0, fs=fs)
    return signal.sosfilt(signal.tf2sos(b, a), y)












# ══════════════════════════════════════════════════════════════════
#  评价工具
# ══════════════════════════════════════════════════════════════════
def tone_amplitude(x, f0, fs=FS):
    """
    用单频正交解调量某个频率成分的幅度
    """
    n = np.arange(len(x))
    c = np.cos(2 * np.pi * f0 * n / fs)
    s = np.sin(2 * np.pi * f0 * n / fs)
    return 2.0 * np.hypot(np.mean(x * c), np.mean(x * s))


def find_r_peaks(x, fs=FS):
    """
    Pan-Tompkins QRS位置检测
    """
    if abs(x.max()) < abs(x.min()):        #翻转正向R峰
        x = -x
    d = np.diff(x, prepend=x[0])
    e = d * d
    win = max(int(0.10 * fs), 1)
    e = np.convolve(e, np.ones(win) / win, mode='same')
    thr = 0.35 * np.percentile(e, 98)
    peaks, _ = signal.find_peaks(e, height=thr, distance=int(0.25 * fs))
    return peaks


def qrs_amplitude(x, peaks, fs=FS, half_ms=60):
    """
    整段信号的 QRS 幅度
    """
    if len(peaks) == 0:
        return np.nan
    h = int(half_ms * fs / 1000)
    vals = []
    for p in peaks:
        a, b = max(0, p - h), min(len(x), p + h + 1)
        if b - a > 3:
            vals.append(x[a:b].max() - x[a:b].min())
    return float(np.median(vals)) if vals else np.nan


def heart_rate(peaks, fs=FS):
    """
    计算BPM
    """
    if len(peaks) < 2:
        return np.nan
    rr = np.diff(peaks) / fs
    rr = rr[(rr > 0.25) & (rr < 2.5)]
    return float(60.0 / np.median(rr)) if len(rr) else np.nan

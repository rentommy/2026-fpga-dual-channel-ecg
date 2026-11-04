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
def chain_hw(x, k=7, notch_q=30.0, n_taps=31, fs=FS, stages=1):
    """
    stages连级数 默认 1，保持与之前的候选对比结果完全一致；
    定稿用 stages=2（见 src/hls/ecg_filter_coef.h 的 DC_STAGES）
    """
    y = dc_block_cascade(x, k, stages)
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









# ══════════════════════════════════════════════════════════════════
#  ①′ 直流阻断（定稿版）：温和高通 + 矩形窗基线估计 + 延迟补偿
#
#  和 ① 的级联移位高通比，差别只在"基线怎么估"：
#    级联移位：一阶 IIR 估基线，群延迟随频率变 11 倍（0.05~1 Hz 内 22~249 点），
#              一个固定延迟量对不齐，残余相位把 T 波削掉一半
#    矩形窗  ：群延迟恒为 (L-1)/2，所有频率一次对齐
#
#  L 必须取到接近一个心拍（实测 RR 824/878 ms）。窗比一拍短的话窗里装着
#  QRS 和 T 波本身，会把基线估计顶高，减完造成 ST 系统性读低
#  —— L=256(512ms) 实测偏差 -0.068 mV，L=320(640ms) 降到 -0.028 mV。
#
#  硬件代价：一条滑动求和（加一次减一次）+ 一次常数乘法（归一化 1/L）
#            + 一条 L 深的历史 RAM + 一条 D 深的延迟线
# ══════════════════════════════════════════════════════════════════
def boxcar_lp(x, L):
    """
    计算基线

    矩形窗滑动平均
    硬件里不做 L 次加法，而是维护一个滑动和：
        sum += x[n] - x[n-L]
        lp   = sum / L
    每点只要一次加、一次减、一次乘（乘 1/L 的定点常数）
    """
    x = np.asarray(x, dtype=np.float64)
    c = np.cumsum(np.concatenate([[0.0], x]))
    out = np.empty(len(x), dtype=np.float64)
    for n in range(len(x)):
        a = max(0, n + 1 - L)
        out[n] = (c[n + 1] - c[a]) / L   # 固定除以 L —— 硬件的历史 RAM 清零启动，
    #                                      窗没填满时等于拿 0 去补，没有除法器可以按实际点数平均。
    #                                      前 L 个点因此是无效输出，上板丢弃（ECG_WARMUP）
    return out


def dc_block_boxcar(x, k_g=8, L=320, D=159):
    """
    定稿直流阻断

        acc += (x - acc) >> k_g        温和高通，fc = fs/(2π·2^k_g) = 0.311 Hz
        yg   = x - acc                 只去直流和极慢漂移，心电频段几乎不动
        lp   = boxcar(yg, L)           估计 yg 里剩下的漂移，滞后恒为 (L-1)/2
        y    = yg[n-D] - lp[n]         把信号延迟 D 点，和 lp 的滞后对上

    D 是**每通道可配**的：D=(L-1)/2 时低频对齐最准（诊断通路），
    D=0 时无额外延迟但相位不补（低延迟通路，给肌电一类闭环场景用）。
    """
    yg = dc_block_shift(np.asarray(x, dtype=np.float64), k_g)                 #直流阻断
    lp = boxcar_lp(yg, L)                                                     #计算基线
    ygd = np.concatenate([np.zeros(D), yg[:len(yg) - D]]) if D else yg        #延迟对齐
    return ygd - lp                                                           #去掉基线漂移


def dc_block_boxcar_delay(D, n_taps=31):                                      #计算信号延迟
    """
    整条链的总延迟（采样点）：延迟线 D + FIR 群延迟

    不收 L —— 矩形窗那 (L-1)/2 的滞后在**被减掉的那一支**上，不在信号通路上。
    它只决定 D 该取多少，不往总延迟上再加一笔：L 从 320 换到 512、D 不变时，
    实测总延迟一点不动（都是 174 点）。
    陷波器也没算：它在 10 Hz 以下群延迟只有 0.11 点，相对 174 点可忽略。
    """
    return D + fir_group_delay(n_taps)


def chain_hw_v2(x, k_g=8, L=320, D=159, notch_q=15.0, n_taps=31, fs=FS):      #理论完整滤波链路
    """
    定稿硬件链：矩形窗直流阻断 → 50Hz 陷波 → 31 抽头 FIR 低通
    参数默认值与 src/hls/ecg_filter_coef.h 一致
    """
    y = dc_block_boxcar(x, k_g, L, D)
    b, a = notch_coef(50.0, notch_q, fs)
    y = notch_apply(y, b, a)
    return fir_apply(y, fir_lowpass(n_taps, 40.0, fs))

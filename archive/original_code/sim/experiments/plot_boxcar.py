# -*- coding: utf-8 -*-
"""
矩形窗基线估计 + 延迟补偿（L=320 / D=159）的效果图

和 F（一阶 IIR + D=200）只差一个零件：基线估计器。
一阶 IIR 的群延迟在 0.05~1 Hz 间变 11 倍，一个 D 只能对齐一个频率；
矩形窗的群延迟恒为 (L-1)/2，D=159 一次对齐全部频率。

L 必须取到接近一个心拍（实测 RR 约 824/878 ms）：窗比一拍短的话，
窗里装着 QRS 和 T 波本身，会把基线估计顶高，减完造成 ST 系统性读低。
L=256（512 ms）时这个偏差是 -0.068 mV，L=320（640 ms）降到 -0.028 mV。

图里的时间窗固定取 20~26 秒，不是挑出来的
（上一轮画 F 的时候挑了 w 最大的窗，结果对 F 有利，这次不挑）。

四条曲线为了能并排看，都按各自实测的 R 峰偏移对齐回去了，
偏移量标在图例里 —— 对齐只是为了看形状，实际系统里是真的晚那么多。
"""
import os
import sys

import numpy as np
from scipy import signal

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'ps'))
sys.path.insert(0, HERE)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib import gridspec                      # noqa: E402

import hw_filter_ref as hw                           # noqa: E402

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 下面四样原先从 sim/experiments/nonlinear_dc.py 取。那个文件属于已否证的
# 非线性探索，2026-10-19 随探索脚本一起归档到 old/nonlinear_gated/。
# 本脚本出的是现行定稿的图，不应该依赖 old/，所以把用到的四样照搬过来，
# 定义与 nonlinear_dc.py 里完全一致（抄的时候核对过）。
FS = hw.FS
LSB_MV = hw.LSB_UV / 1000.0
WANDER_SOS = signal.butter(4, [0.05, 0.5], btype='bandpass', fs=FS, output='sos')


def full_chain(dc_out):
    """直流阻断之后的两级固定不变：陷波 Q=15 + 31 抽头 FIR"""
    y = hw.notch_apply(dc_out, *hw.notch_coef(50.0, 15.0, FS))
    return hw.fir_apply(y, hw.fir_lowpass(31, 40.0, FS))

K_G, L_BOX, D_BOX, D_IIR = 8, 320, 159, 200
PQ, ST, TW = (-45, -20), (50, 60), (75, 200)         # 相对 R 峰的采样窗（点）


def shift_lp(x, k):
    s = 1.0 / (1 << k)
    return signal.lfilter([s], [1.0, -(1.0 - s)], x)


def delay(x, d):
    return np.concatenate([np.zeros(d), x[:len(x) - d]]) if d else x


def boxcar_lp(x, L):
    """滑动求和：硬件里是 sum += x[n]-x[n-L]，再右移 log2(L) 位"""
    return signal.lfilter(np.ones(L) / L, [1.0], x)


def chain_box(x):
    yg = hw.dc_block_cascade(x, K_G, 1)
    return delay(yg, D_BOX) - boxcar_lp(yg, L_BOX)


def chain_iir(x):
    yg = hw.dc_block_cascade(x, K_G, 1)
    return delay(yg, D_IIR) - shift_lp(yg, K_G)


def per_beat(y, peaks):
    """逐拍测量，全部以同一拍 PQ 等电位段为基准"""
    out = []
    for p in peaks:
        if p + PQ[0] < 0 or p + TW[1] >= len(y):
            continue
        ref = np.mean(y[p + PQ[0]:p + PQ[1]])
        out.append((p, (np.mean(y[p + ST[0]:p + ST[1]]) - ref) * LSB_MV,
                    (np.max(y[p + TW[0]:p + TW[1]]) - ref) * LSB_MV))
    return np.array(out)


def pair(a, b, tol=40):
    sh = int(np.median([a[i, 0] - b[min(i, len(b) - 1), 0]
                        for i in range(min(len(a), len(b)))]))
    pa, pb = [], []
    for row in a:
        j = int(np.argmin(np.abs(b[:, 0] + sh - row[0])))
        if abs(b[j, 0] + sh - row[0]) <= tol:
            pa.append(row[1:])
            pb.append(b[j, 1:])
    return np.array(pa), np.array(pb)


def template(y, peaks, A=125, B=200):
    segs = np.array([y[p - A:p + B] for p in peaks
                     if p - A >= 0 and p + B <= len(y)])
    m = segs.mean(axis=0) * LSB_MV
    return m - np.median(m[:25])                     # 以拍首为零


def load(p):
    v = []
    with open(p, encoding='utf-8', errors='ignore') as f:
        for ln in f:
            try:
                v.append(int(ln.strip()))
            except ValueError:
                pass
    return np.array(v, dtype=np.float64)


raw = load(os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt'))
ref = hw.chain_orig_zerophase(raw)
ref_pk = hw.find_r_peaks(ref)

CAND = [
    ('零相位参考 filtfilt（非因果，只作基准）', ref, 'k', 1.6),
    ('定稿 LTI k=7x2', full_chain(hw.dc_block_cascade(raw, 7, 2)), 'tab:red', 1.1),
    (f'F 一阶IIR + D={D_IIR}', full_chain(chain_iir(raw)), 'tab:orange', 1.1),
    (f'矩形窗 L={L_BOX} + D={D_BOX}', full_chain(chain_box(raw)), 'tab:blue', 1.4),
]

# 实测各自的 R 峰偏移，画图时对齐回去
rows = []
for nm, y, col, lw in CAND:
    pk = hw.find_r_peaks(y)
    n = min(len(pk), len(ref_pk))
    sh = int(round(float(np.median(pk[:n] - ref_pk[:n]))))
    wd = signal.sosfiltfilt(WANDER_SOS, y) * LSB_MV
    W = 2 * FS
    seg = wd[:len(wd) // W * W].reshape(-1, W)
    typ = float(np.median(seg.max(axis=1) - seg.min(axis=1)))
    rows.append(dict(name=nm, y=y, c=col, lw=lw, sh=sh, pk=pk, wd=wd, typ=typ))

ref_bb = per_beat(ref, ref_pk)
for r in rows[1:]:
    A, B = pair(per_beat(r['y'], r['pk']), ref_bb)
    e = A - B
    r['st'] = e[:, 0]
    r['tp'] = e[:, 1]

fig = plt.figure(figsize=(15, 13))
gs = gridspec.GridSpec(4, 3, height_ratios=[1.0, 1.5, 1.0, 1.25], hspace=0.42,
                       wspace=0.28)

# ① 矩形窗在估什么：温和高通输出 + 对齐后的基线估计
ax = fig.add_subplot(gs[0, :])
t0, t1 = 20 * FS, 26 * FS
tt = np.arange(t0, t1) / FS
yg = hw.dc_block_cascade(raw, K_G, 1)
lp = boxcar_lp(yg, L_BOX)
ax.plot(tt, yg[t0:t1] * LSB_MV, color='0.55', lw=0.9,
        label=f'温和高通输出 yg（k_g={K_G}，仍含漂移）')
ax.plot(tt, lp[t0 + D_BOX:t1 + D_BOX] * LSB_MV, color='tab:blue', lw=2.0,
        label=f'矩形窗基线估计 lp（已按 D={D_BOX} 对齐到 yg 上）')
ax.plot(tt, shift_lp(yg, K_G)[t0 + D_IIR:t1 + D_IIR] * LSB_MV,
        color='tab:orange', lw=1.6, ls='--',
        label=f'一阶IIR 基线估计（按 D={D_IIR} 对齐，对不齐的部分就是残余相位）')
ax.set_ylabel('mV')
ax.set_title('① 两种基线估计器在估同一条基线：矩形窗群延迟恒定 159.5 点，'
             '一阶IIR 在 0.05~1 Hz 间变 11 倍', fontsize=11)
ax.legend(fontsize=8.5, loc='upper right')
ax.grid(alpha=0.3)

# ② 输出波形对比（固定窗 20~26 s，各自按实测偏移对齐）
ax = fig.add_subplot(gs[1, :])
for r in rows:
    a, b = t0 + r['sh'], t1 + r['sh']
    ax.plot(tt, r['y'][a:b] * LSB_MV, color=r['c'], lw=r['lw'],
            label=f"{r['name']}（实测晚 {r['sh']} 点 = {r['sh']/FS*1000:.0f} ms）")
ax.set_ylabel('mV')
ax.set_title('② 滤波输出对比（固定取 20~26 秒，不是挑的；'
             '为看形状已按各自实测延迟对齐）', fontsize=11)
ax.legend(fontsize=8.5, ncol=2, loc='upper right')
ax.grid(alpha=0.3)

# ③ 残留基线（0.05~0.5 Hz 带），整段
ax = fig.add_subplot(gs[2, :])
ta = np.arange(len(raw)) / FS
for r in rows[1:]:
    ax.plot(ta, r['wd'], color=r['c'], lw=1.0,
            label=f"{r['name']}：2秒窗中位 {r['typ']:.3f} mV")
ax.axhspan(-0.05, 0.05, color='tab:green', alpha=0.12, label='±0.05 mV 参照带')
ax.set_xlabel('时间 (s)')
ax.set_ylabel('mV')
ax.set_title('③ 残留基线漂移（0.05~0.5 Hz 带，整段 60 秒）', fontsize=11)
ax.legend(fontsize=8.5, loc='upper right')
ax.grid(alpha=0.3)

# ④ 平均心拍
ax = fig.add_subplot(gs[3, 0])
tb = (np.arange(-125, 200)) / FS * 1000
for r in rows:
    ax.plot(tb, template(r['y'], r['pk']), color=r['c'], lw=r['lw'])
ax.axvspan(PQ[0] / FS * 1000, PQ[1] / FS * 1000, color='gray', alpha=0.18)
ax.axvspan(ST[0] / FS * 1000, ST[1] / FS * 1000, color='tab:green', alpha=0.18)
ax.axvspan(TW[0] / FS * 1000, TW[1] / FS * 1000, color='orange', alpha=0.10)
ax.text(-78, ax.get_ylim()[1] * 0.92, 'PQ', fontsize=8, color='0.3')
ax.text(104, ax.get_ylim()[1] * 0.92, 'ST60', fontsize=8, color='tab:green')
ax.text(230, ax.get_ylim()[1] * 0.92, 'T 波', fontsize=8, color='darkorange')
ax.set_xlabel('相对 R 峰 (ms)')
ax.set_ylabel('mV')
ax.set_title('④ 平均心拍（73 拍）', fontsize=11)
ax.grid(alpha=0.3)

# ⑤ 逐拍 ST60 误差分布
ax = fig.add_subplot(gs[3, 1])
for i, r in enumerate(rows[1:]):
    ax.hist(r['st'], bins=22, histtype='step', lw=1.6, color=r['c'],
            label=f"RMS {r['st'].std():.4f}")
ax.axvline(0, color='k', ls='--', lw=0.8)
ax.set_xlabel('逐拍 ST60 误差 (mV)')
ax.set_ylabel('拍数')
ax.set_title('⑤ 逐拍 ST60 误差（越窄越好）', fontsize=11)
ax.legend(fontsize=8.5)
ax.grid(alpha=0.3)

# ⑥ 逐拍 T 峰误差分布
ax = fig.add_subplot(gs[3, 2])
for r in rows[1:]:
    ax.hist(r['tp'], bins=22, histtype='step', lw=1.6, color=r['c'],
            label=f"RMS {r['tp'].std():.4f}")
ax.axvline(0, color='k', ls='--', lw=0.8)
ax.set_xlabel('逐拍 T 峰误差 (mV)')
ax.set_title('⑥ 逐拍 T 峰误差', fontsize=11)
ax.legend(fontsize=8.5)
ax.grid(alpha=0.3)

fig.suptitle(f'矩形窗基线估计 L={L_BOX} + 延迟补偿 D={D_BOX}（零乘法器）'
             f'  —  调参段 60 s / 500 SPS', fontsize=13, y=0.995)
out = os.path.join(HERE, 'boxcar_L320_D159.png')
plt.savefig(out, dpi=140, bbox_inches='tight')
plt.close()

print(f'已保存 {out}\n')
print(f"{'方案':<34}{'实测延迟':>10}{'典型漂移':>10}{'ST60 RMS':>11}{'T峰 RMS':>10}")
print('-' * 76)
for r in rows:
    if 'st' not in r:
        print(f"{r['name']:<34}{r['sh']:>7} 点{'-':>10}{'-':>11}{'-':>10}")
        continue
    print(f"{r['name']:<34}{r['sh']:>7} 点{r['typ']:>10.3f}"
          f"{r['st'].std():>11.4f}{r['tp'].std():>10.4f}")

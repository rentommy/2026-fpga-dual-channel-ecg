# -*- coding: utf-8 -*-
"""
把双链合并的两条链画出来 -- 温和链更温和、强链更强烈的那组参数

参数取联合扫描选出的工作点：温和 k=8 一级（不门控）+ 强 k=6 两级（门控 thr=400）

三张图：
  上  一段含基线摆动的时间窗，看两条链各自什么样、合并输出落在哪
  中  合并权重 w，看强链什么时候才被调进来
  下  按 R 波对齐的平均心拍，看形态上两条链差在哪、合并后像谁
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import signal

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'ps'))
sys.path.insert(0, HERE)

import hw_filter_ref as hw            # noqa: E402
import nonlinear_dc as nl             # noqa: E402

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
FS, LSB_MV = nl.FS, nl.LSB_MV
K_G, K_A, ST_A, THR = 8, 6, 2, 400


def gentle(x, k):
    c = 1.0 - 1.0 / (1 << k)
    return signal.lfilter([c, -c], [1.0, -c], x)


def aggr_gated(x, k, stages, thr):
    s = 1.0 / (1 << k)
    acc = np.zeros(stages)
    y = np.empty(len(x))
    prev = x[0]
    for n in range(len(x)):
        g = abs(x[n] - prev) >= thr
        prev = x[n]
        u = x[n]
        for j in range(stages):
            if not g:
                acc[j] += (u - acc[j]) * s
            u = u - acc[j]
        y[n] = u
    return y


def tmpl(x, peaks, A, B):
    segs = np.array([x[p - A:p + B] for p in peaks
                     if p - A >= 0 and p + B <= len(x)])
    return segs.mean(axis=0)


raw = nl.load()
yg = gentle(raw, K_G)
ya = aggr_gated(raw, K_A, ST_A, THR)
d = np.abs(yg - ya)
lo, hi = np.percentile(d, 50), np.percentile(d, 99)
w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
y = yg + w * (ya - yg)
ref = hw.chain_orig_zerophase(raw)

# 挑一段权重动得最厉害的窗口，摆动在那里
sk = 2 * FS
win = int(8 * FS)
wsm = np.convolve(w[sk:], np.ones(win) / win, mode='valid')
c0 = int(np.argmax(wsm)) + sk
a, b = max(sk, c0), min(len(raw), c0 + win)
t = np.arange(a, b) / FS

fig, ax = plt.subplots(3, 1, figsize=(13, 11),
                       gridspec_kw={'height_ratios': [2.6, 1, 2.4]})

ax[0].plot(t, yg[a:b] * LSB_MV, lw=1.0, color='tab:blue', alpha=0.85,
           label=f'温和链  k={K_G} 一级（不门控）-- 保形态，漂移压不住')
ax[0].plot(t, ya[a:b] * LSB_MV, lw=1.0, color='tab:orange', alpha=0.85,
           label=f'强阻断链 k={K_A} 两级（门控 thr={THR}）-- 压漂移，吃 T 波')
ax[0].plot(t, y[a:b] * LSB_MV, lw=1.5, color='k',
           label='合并输出')
ax[0].set_ylabel('mV')
ax[0].set_title('双链路直流阻断：两条链与合并输出（含一段基线摆动）')
ax[0].legend(loc='upper right', fontsize=9)
ax[0].grid(alpha=0.3)

ax[1].fill_between(t, 0, w[a:b], color='tab:green', alpha=0.35)
ax[1].plot(t, w[a:b], color='tab:green', lw=1.2)
ax[1].set_ylabel('权重 w')
ax[1].set_xlabel('时间 (s)')
ax[1].set_ylim(-0.03, 1.03)
ax[1].set_title(f'w=0 全走温和链，w=1 全走强阻断链（全段均值 {w.mean():.3f}）',
                fontsize=10)
ax[1].grid(alpha=0.3)

A, B = int(0.3 * FS), int(0.5 * FS)
tt = np.arange(-A, B) / FS * 1000
pk = hw.find_r_peaks(nl.full_chain(y))
for sig, lab, col, lw_ in (
        (nl.full_chain(yg), '温和链', 'tab:blue', 1.2),
        (nl.full_chain(ya), '强阻断链', 'tab:orange', 1.2),
        (nl.full_chain(y), '合并输出', 'k', 1.8),
        (ref, '零相移参考（上限）', 'tab:red', 1.2)):
    m = tmpl(sig, pk, A, B) * LSB_MV
    ax[2].plot(tt, m - np.median(m[:int(0.05 * FS)]), lw=lw_, color=col,
               ls='--' if lab.startswith('零相移') else '-', label=lab)
ax[2].axvspan(80, 400, color='orange', alpha=0.10, label='ST-T 段')
ax[2].axvline(0, color='gray', ls=':', lw=0.8)
ax[2].set_xlabel('相对 R 波峰的时间 (ms)')
ax[2].set_ylabel('mV')
ax[2].set_title('平均心拍（过完整条链）-- 强阻断链在 ST-T 段把 T 波削掉了一块')
ax[2].legend(fontsize=9)
ax[2].grid(alpha=0.3)

plt.tight_layout()
out = os.path.join(HERE, 'dual_chain.png')
plt.savefig(out, dpi=140)
print(f'已画出 {out}')
print(f'窗口 {a/FS:.1f}~{b/FS:.1f} 秒，该窗内 w 均值 {w[a:b].mean():.3f}，'
      f'峰值 {w[a:b].max():.3f}')
print(f'全段 w：均值 {w.mean():.3f}，w<0.05 占 {np.mean(w < 0.05)*100:.0f}%，'
      f'w>0.5 占 {np.mean(w > 0.5)*100:.1f}%')

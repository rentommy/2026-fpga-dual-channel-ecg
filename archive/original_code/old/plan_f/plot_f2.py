# -*- coding: utf-8 -*-
"""
方案 F 定稿版（带延迟对齐 D=80）的输出图

  acc += (x - acc) >> 8           温和高通
  yg   = x - acc
  lp  += (yg - lp) >> 8           估计 yg 里残留的基线（滞后约 0.5 秒）
  w    = clip((|lp| - lo)/(hi - lo), 0, 1)
  y    = delay(yg, 80) - w * lp   信号通路延迟 80 点，和估计对齐

D=80 来自细扫：D=40~140 是一片平台地（最差漂移 1.27~1.29），
形态在 80 处达峰。理论群延迟随频率变（直流 256 点、0.2Hz 181 点、
0.5Hz 71 点），所以不存在能全对齐的单一值，80 相当于对齐 0.45Hz 附近。
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
sys.path.insert(0, os.path.join(ROOT, 'old', 'nonlinear_gated'))   # 2026-10-19 归档：公共模块在隔壁

import hw_filter_ref as hw            # noqa: E402
import nonlinear_dc as nl             # noqa: E402

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
FS, LSB_MV = nl.FS, nl.LSB_MV
K_G, K_LP, DLY = 8, 8, 80


def plan_F(x, D):
    c = 1.0 - 1.0 / (1 << K_G)
    yg = signal.lfilter([c, -c], [1.0, -c], x)
    s = 1.0 / (1 << K_LP)
    lp = signal.lfilter([s], [1.0, -(1.0 - s)], yg)
    d = np.abs(lp)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    ygd = np.concatenate([np.zeros(D), yg[:len(yg) - D]]) if D else yg
    return ygd - w * lp, yg, ygd, lp, w


def tmpl(x, peaks, A, B):
    sg = np.array([x[p - A:p + B] for p in peaks
                   if p - A >= 0 and p + B <= len(x)])
    m = sg.mean(axis=0) * LSB_MV
    return m - np.median(m[:int(0.05 * FS)])


raw = nl.load()
y80, yg, ygd, lp, w = plan_F(raw, DLY)
y00 = plan_F(raw, 0)[0]
y_lti = hw.dc_block_cascade(raw, 7, 2)
ref = hw.chain_orig_zerophase(raw)
oF, oL = nl.full_chain(y80), nl.full_chain(y_lti)

sk, win = 2 * FS, int(8 * FS)
wsm = np.convolve(w[sk:], np.ones(win) / win, mode='valid')
c0 = int(np.argmax(wsm)) + sk
a, b = max(sk, c0), min(len(raw), c0 + win)
t = np.arange(a, b) / FS

fig, ax = plt.subplots(4, 1, figsize=(13, 14),
                       gridspec_kw={'height_ratios': [2.3, 0.85, 2.3, 2.3]})

ax[0].plot(t, yg[a:b] * LSB_MV, lw=0.9, color='tab:cyan', alpha=0.55,
           label='yg  温和高通输出（未延迟）')
ax[0].plot(t, ygd[a:b] * LSB_MV, lw=1.1, color='tab:blue',
           label=f'yg 延迟 {DLY} 点（160 ms）')
ax[0].plot(t, lp[a:b] * LSB_MV, lw=2.2, color='tab:red',
           label='lp  估出的残留基线（本身滞后约 0.5 s）')
ax[0].axhline(0, color='gray', lw=0.6, ls=':')
ax[0].set_ylabel('mV')
ax[0].set_title('① 延迟对齐：把信号往右挪 80 点，去对上滞后的基线估计（红）')
ax[0].legend(loc='upper right', fontsize=9)
ax[0].grid(alpha=0.3)

ax[1].fill_between(t, 0, w[a:b], color='tab:green', alpha=0.35)
ax[1].plot(t, w[a:b], color='tab:green', lw=1.2)
ax[1].set_ylabel('权重 w')
ax[1].set_ylim(-0.03, 1.03)
ax[1].set_title(f'② 回减力度 w（均值 {w.mean():.3f}，'
                f'w<0.05 占 {np.mean(w < 0.05)*100:.0f}% 的时间）', fontsize=10)
ax[1].grid(alpha=0.3)

def p2p(s):
    z = signal.sosfiltfilt(nl.WANDER_SOS, s)
    return (z.max() - z.min()) * LSB_MV

ax[2].plot(t, y00[a:b] * LSB_MV, lw=1.0, color='tab:orange', alpha=0.9,
           label=f'F 不补偿 D=0        漂移峰峰 {p2p(y00):.3f} mV')
ax[2].plot(t, y_lti[a:b] * LSB_MV, lw=1.0, color='tab:purple', alpha=0.8,
           label=f'定稿 LTI k=7×2 级    漂移峰峰 {p2p(y_lti):.3f} mV')
ax[2].plot(t, y80[a:b] * LSB_MV, lw=1.4, color='k',
           label=f'F 补偿 D=80          漂移峰峰 {p2p(y80):.3f} mV')
ax[2].axhline(0, color='gray', lw=0.6, ls=':')
ax[2].set_ylabel('mV')
ax[2].set_xlabel('时间 (s)')
ax[2].set_title('③ 直流阻断级输出 —— 对齐之后基线比定稿还平')
ax[2].legend(loc='upper right', fontsize=9)
ax[2].grid(alpha=0.3)

A, B = int(0.3 * FS), int(0.5 * FS)
tt = np.arange(-A, B) / FS * 1000
# 每条信号用它自己的 R 峰 —— F 已经延迟 80 点，共用峰位会错开 160 ms
mF, mL, mR = (tmpl(s, hw.find_r_peaks(s), A, B) for s in (oF, oL, ref))
pk = hw.find_r_peaks(oF)
rng = slice(A + 60, A + 200)
ax[3].plot(tt, mR, lw=1.3, color='tab:red', ls='--',
           label=f'零相移参考（上限）  T波 {mR[rng].max():.3f} mV')
ax[3].plot(tt, mF, lw=2.0, color='k',
           label=f'方案 F  D=80         T波 {mF[rng].max():.3f} mV')
ax[3].plot(tt, mL, lw=1.3, color='tab:purple',
           label=f'定稿 LTI k7×2        T波 {mL[rng].max():.3f} mV')
ax[3].axvspan(80, 400, color='orange', alpha=0.10, label='ST-T 段')
ax[3].axvline(0, color='gray', ls=':', lw=0.8)
ax[3].set_xlabel('相对 R 波峰的时间 (ms)')
ax[3].set_ylabel('mV')
ax[3].set_title('④ 平均心拍 —— T 波和 ST 段基本贴着参考走')
ax[3].legend(fontsize=9)
ax[3].grid(alpha=0.3)

plt.tight_layout()
out = os.path.join(HERE, 'plan_F_aligned.png')
plt.savefig(out, dpi=140)
print(f'已画出 {out}')
print(f'窗口 {a/FS:.1f}~{b/FS:.1f} 秒')
print(f'漂移峰峰：F不补偿 {p2p(y00):.3f} / 定稿 {p2p(y_lti):.3f} / '
      f'F补偿D=80 {p2p(y80):.3f} mV')
print(f'T 波峰值：参考 {mR[rng].max():.3f} / F {mF[rng].max():.3f} / '
      f'定稿 {mL[rng].max():.3f} mV')

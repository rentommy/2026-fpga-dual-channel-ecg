# -*- coding: utf-8 -*-
"""
方案 F（单链自残基线回减）的输出图

  acc += (x - acc) >> 8        温和高通
  yg   = x - acc
  lp  += (yg - lp) >> 8        估计 yg 里残留的基线
  w    = clip((|lp| - lo)/(hi - lo), 0, 1)
  y    = yg - w * lp           按需回减

四张图：
  1  机理：温和链输出 yg、估出来的残留基线 lp、回减后的 y
  2  权重 w
  3  过完整条链之后，F / 定稿 / 零相移参考 的实际波形
  4  平均心拍 -- 看 T 波被保住了多少
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
K_G, K_LP = 8, 8


def gentle(x, k):
    c = 1.0 - 1.0 / (1 << k)
    return signal.lfilter([c, -c], [1.0, -c], x)


def shift_lp(x, k):
    s = 1.0 / (1 << k)
    return signal.lfilter([s], [1.0, -(1.0 - s)], x)


def plan_F(x):
    yg = gentle(x, K_G)
    lp = shift_lp(yg, K_LP)
    d = np.abs(lp)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg - w * lp, yg, lp, w


def tmpl(x, peaks, A, B):
    segs = np.array([x[p - A:p + B] for p in peaks
                     if p - A >= 0 and p + B <= len(x)])
    m = segs.mean(axis=0) * LSB_MV
    return m - np.median(m[:int(0.05 * FS)])


raw = nl.load()
y, yg, lp, w = plan_F(raw)
y_lti = hw.dc_block_cascade(raw, 7, 2)
ref = hw.chain_orig_zerophase(raw)
out_F = nl.full_chain(y)
out_L = nl.full_chain(y_lti)

# 选一段权重动得厉害的窗口，摆动在那儿
sk, win = 2 * FS, int(8 * FS)
wsm = np.convolve(w[sk:], np.ones(win) / win, mode='valid')
c0 = int(np.argmax(wsm)) + sk
a, b = max(sk, c0), min(len(raw), c0 + win)
t = np.arange(a, b) / FS

fig, ax = plt.subplots(4, 1, figsize=(13, 14),
                       gridspec_kw={'height_ratios': [2.4, 0.9, 2.4, 2.4]})

ax[0].plot(t, yg[a:b] * LSB_MV, lw=1.0, color='tab:blue', alpha=0.8,
           label='yg  温和高通输出（k=8，基线还剩不少）')
ax[0].plot(t, lp[a:b] * LSB_MV, lw=2.0, color='tab:red',
           label='lp  估出来的残留基线（低通 k=8）')
ax[0].plot(t, y[a:b] * LSB_MV, lw=1.3, color='k',
           label='y = yg - w*lp  回减之后')
ax[0].axhline(0, color='gray', lw=0.6, ls=':')
ax[0].set_ylabel('mV')
ax[0].set_title('① 机理：低通估出残留基线（红），按权重回减掉')
ax[0].legend(loc='upper right', fontsize=9)
ax[0].grid(alpha=0.3)

ax[1].fill_between(t, 0, w[a:b], color='tab:green', alpha=0.35)
ax[1].plot(t, w[a:b], color='tab:green', lw=1.2)
ax[1].set_ylabel('权重 w')
ax[1].set_ylim(-0.03, 1.03)
ax[1].set_title(f'② 回减力度 w（全段均值 {w.mean():.3f}，'
                f'w<0.05 占 {np.mean(w < 0.05)*100:.0f}%）', fontsize=10)
ax[1].grid(alpha=0.3)

ax[2].plot(t, out_L[a:b] * LSB_MV, lw=1.0, color='tab:orange', alpha=0.9,
           label='定稿 LTI k=7×2 级')
ax[2].plot(t, out_F[a:b] * LSB_MV, lw=1.2, color='k', label='方案 F')
ax[2].plot(t, ref[a:b] * LSB_MV, lw=1.0, color='tab:red', ls='--',
           alpha=0.7, label='零相移参考（硬件做不到，仅作上限）')
ax[2].set_ylabel('mV')
ax[2].set_xlabel('时间 (s)')
ax[2].set_title('③ 过完整条链之后的实际波形 —— F 的基线比定稿晃，但波形更完整')
ax[2].legend(loc='upper right', fontsize=9)
ax[2].grid(alpha=0.3)

A, B = int(0.3 * FS), int(0.5 * FS)
tt = np.arange(-A, B) / FS * 1000
pk = hw.find_r_peaks(out_F)
mF, mL, mR = (tmpl(s, pk, A, B) for s in (out_F, out_L, ref))
ax[3].plot(tt, mR, lw=1.3, color='tab:red', ls='--',
           label=f'零相移参考（上限）  T波 {mR[A+60:A+200].max():.3f} mV')
ax[3].plot(tt, mF, lw=2.0, color='k',
           label=f'方案 F                T波 {mF[A+60:A+200].max():.3f} mV')
ax[3].plot(tt, mL, lw=1.3, color='tab:orange',
           label=f'定稿 LTI k7×2         T波 {mL[A+60:A+200].max():.3f} mV')
ax[3].axvspan(80, 400, color='orange', alpha=0.10, label='ST-T 段')
ax[3].axvline(0, color='gray', ls=':', lw=0.8)
ax[3].set_xlabel('相对 R 波峰的时间 (ms)')
ax[3].set_ylabel('mV')
ax[3].set_title('④ 平均心拍 —— 定稿把 T 波削掉一半多，F 基本保住')
ax[3].legend(fontsize=9)
ax[3].grid(alpha=0.3)

plt.tight_layout()
out = os.path.join(HERE, 'plan_F.png')
plt.savefig(out, dpi=140)
print(f'已画出 {out}')
print(f'窗口 {a/FS:.1f}~{b/FS:.1f} 秒')
print(f'T 波峰值：参考 {mR[A+60:A+200].max():.3f} / '
      f'F {mF[A+60:A+200].max():.3f} / 定稿 {mL[A+60:A+200].max():.3f} mV')

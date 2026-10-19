# -*- coding: utf-8 -*-
"""
方案 F 的残留基线估计有滞后 -- 补偿一下能不能救（用户发现）

lp 是一阶因果低通，k=8 时时间常数 2^8/500 = 0.512 秒。
它估出来的基线滞后约半秒，等于在用"半秒前的基线"去减现在的信号。
原实现 y = yg - w*lp 没有任何对齐。

补偿做法：把信号通路延迟 D 个点，让它和 lp 的滞后对上
    y[n] = yg[n-D] - w[n]*lp[n]
代价是整条链多 D 点延迟（FIR 已有 15 点）。

但一阶 IIR 低通的群延迟是**随频率变的**：
    tau(f) = tau0 / (1 + (f/fc)^2)
k=8 时 fc=0.311Hz，0.05Hz 处 0.499 秒，0.5Hz 处 0.143 秒 -- 差 3.5 倍。
所以单一延迟量只能对齐一个频率，不可能全对上。扫一遍看能救回多少。
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
sys.path.insert(0, os.path.join(ROOT, 'old', 'nonlinear_gated'))   # 2026-10-19 归档：公共模块在隔壁

import hw_filter_ref as hw            # noqa: E402
import nonlinear_dc as nl             # noqa: E402
import switch_transient as sw         # noqa: E402

FS, LSB_MV = nl.FS, nl.LSB_MV
K_G = 8
RECORDS = [
    ('调参段', os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')),
    ('验证段', os.path.join(ROOT, 'data', 'source', 'ecg_val_60s_500sps.txt')),
]


def load(p):
    v = []
    with open(p, encoding='utf-8', errors='ignore') as f:
        for ln in f:
            try:
                v.append(int(ln.strip()))
            except ValueError:
                pass
    return np.array(v, dtype=np.float64)


def gentle(x, k):
    c = 1.0 - 1.0 / (1 << k)
    return signal.lfilter([c, -c], [1.0, -c], x)


def shift_lp(x, k):
    s = 1.0 / (1 << k)
    return signal.lfilter([s], [1.0, -(1.0 - s)], x)


def plan_F(x, k_lp, D):
    """D = 信号通路补偿的延迟点数；D=0 即原实现"""
    yg = gentle(x, K_G)
    lp = shift_lp(yg, k_lp)
    d = np.abs(lp)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    ygd = np.concatenate([np.zeros(D), yg[:len(yg) - D]]) if D else yg
    return ygd - w * lp


def t_peak(out, peaks):
    A, B = int(0.3 * FS), int(0.5 * FS)
    segs = np.array([out[p - A:p + B] for p in peaks
                     if p - A >= 0 and p + B <= len(out)])
    if len(segs) < 5:
        return np.nan
    m = segs.mean(axis=0) * LSB_MV
    m = m - np.median(m[:int(0.05 * FS)])
    return float(m[A + int(0.12 * FS):A + int(0.40 * FS)].max())


def score(y, ctx):
    out = nl.full_chain(y)
    pk = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ctx["ref"])
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    ms, ex = sw.match_peaks(pk, ctx["peaks"])[:2]
    return dict(p2p=(wd.max() - wd.min()) * LSB_MV, full=c["全拍"],
                p=c["P段"], stt=c["ST-T"], tp=t_peak(out, pk), bad=ms + ex)


ctxs = []
for nm, p in RECORDS:
    raw = load(p)
    ref = hw.chain_orig_zerophase(raw)
    ctx = dict(name=nm, raw=raw, ref=ref, peaks=hw.find_r_peaks(ref))
    ctx["base"] = score(hw.dc_block_cascade(raw, 7, 2), ctx)
    ctxs.append(ctx)

for k_lp in (8, 9):
    tau0 = (1 << k_lp) / FS
    fc = FS / (2 * np.pi * (1 << k_lp))
    tau02 = tau0 / (1 + (0.2 / fc) ** 2)
    print(f'\n=== 低通 k={k_lp}  fc={fc:.3f}Hz  '
          f'直流处群延迟 {tau0*FS:.0f} 点 ({tau0:.3f}s)，'
          f'0.2Hz 处 {tau02*FS:.0f} 点 ({tau02:.3f}s) ===')
    print(f'{"补偿D":>6}{"":<2}{"调参段漂移":>11}{"验证段漂移":>11}'
          f'{"最差漂移":>10}{"最差全拍":>10}{"最差ST-T":>10}{"最差T波":>9}{"错拍":>5}')
    print('-' * 76)
    for D in (0, 60, 120, 180, 256, 360, 480):
        ss = [score(plan_F(c["raw"], k_lp, D), c) for c in ctxs]
        print(f'{D:>6}{"":<2}{ss[0]["p2p"]:>11.3f}{ss[1]["p2p"]:>11.3f}'
              f'{max(s["p2p"] for s in ss):>10.3f}'
              f'{min(s["full"] for s in ss):>10.4f}'
              f'{min(s["stt"] for s in ss):>10.4f}'
              f'{min(s["tp"] for s in ss):>9.3f}'
              f'{max(s["bad"] for s in ss):>5}')

print(f'\n参照 定稿 LTI k7x2：调参段漂移 {ctxs[0]["base"]["p2p"]:.3f}，'
      f'验证段 {ctxs[1]["base"]["p2p"]:.3f}，'
      f'最差全拍 {min(c["base"]["full"] for c in ctxs):.4f}，'
      f'最差T波 {min(c["base"]["tp"] for c in ctxs):.3f}')

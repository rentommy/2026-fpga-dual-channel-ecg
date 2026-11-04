# -*- coding: utf-8 -*-
"""
方案乙：注入量先低通 -- 只把慢的基线修正注进输出，把 T 波挡在外面

问题（dual_chain.png 直接画出来了）：
    y = y温和 + w*(y强 - y温和)
注入量 (y强 - y温和) 里有 26~52% 是 T 波，所以合并输出的 T 波
从温和链的 0.42 mV 掉到 0.35 mV。掉的那 0.07 就是这么来的。

方案乙：
    corr = 低通(y强 - y温和)      只留 0.5Hz 以下
    y    = y温和 + w * corr
想要的基线摆动在 0.05~0.5 Hz，不想要的 T 波在 1~5 Hz，一道低通切开。

两个变体：
  乙1  检测量 w 也用滤过的 corr   -> 注入污染和检测污染一起解决
  乙2  检测量仍用未滤的差         -> 只改注入，便于区分是哪一处起作用

代价：低通有延迟，修正量会迟到，对突发摆动的响应变慢。要测。
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

import hw_filter_ref as hw            # noqa: E402
import nonlinear_dc as nl             # noqa: E402
import switch_transient as sw         # noqa: E402
import gated_dual as gd               # noqa: E402

FS, LSB_MV = nl.FS, nl.LSB_MV
K_G, K_A, ST_A, THR = 8, 6, 2, 400
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


def shift_lp(x, k):
    """移位式一阶低通，fc = FS/(2*pi*2^k)；零乘法器"""
    s = 1.0 / (1 << k)
    return signal.lfilter([s], [1.0, -(1.0 - s)], x)


def lp_fc(k):
    return FS / (2.0 * np.pi * (1 << k))


def build(raw, k_lp, detect_filtered):
    """k_lp=0 表示不滤（即现状）"""
    yg = gentle(raw, K_G)
    ya = aggr_gated(raw, K_A, ST_A, THR)
    corr_raw = ya - yg
    corr = corr_raw if k_lp == 0 else shift_lp(corr_raw, k_lp)
    d = np.abs(corr if detect_filtered else corr_raw)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg + w * corr, d, w


def t_peak(out, peaks):
    """平均心拍里 T 波的峰值（mV），直接量注入污染的后果"""
    A, B = int(0.3 * FS), int(0.5 * FS)
    segs = np.array([out[p - A:p + B] for p in peaks
                     if p - A >= 0 and p + B <= len(out)])
    if len(segs) < 5:
        return np.nan
    m = segs.mean(axis=0) * LSB_MV
    m = m - np.median(m[:int(0.05 * FS)])
    i0, i1 = A + int(0.12 * FS), A + int(0.40 * FS)
    return float(m[i0:i1].max())


def score(y, d, ctx):
    out = nl.full_chain(y)
    pk = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ctx["ref"])
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    ms, ex = sw.match_peaks(pk, ctx["peaks"])[:2]
    return dict(p2p=(wd.max() - wd.min()) * LSB_MV, full=c["全拍"],
                p=c["P段"], stt=c["ST-T"], bad=ms + ex,
                tp=t_peak(out, pk), poll=gd.pollution(d, pk))


def main():
    ctxs = []
    for nm, p in RECORDS:
        raw = load(p)
        ref = hw.chain_orig_zerophase(raw)
        ctx = dict(name=nm, raw=raw, ref=ref, peaks=hw.find_r_peaks(ref))
        ctx["base"] = score(hw.dc_block_cascade(raw, 7, 2),
                            np.ones(len(raw)), ctx)
        ctx["ref_tp"] = t_peak(ref, ctx["peaks"])
        ctx["g_tp"] = t_peak(nl.full_chain(gentle(raw, K_G)), ctx["peaks"])
        ctxs.append(ctx)
        b = ctx["base"]
        print(f'{nm}: 定稿 漂移 {b["p2p"]:.3f} 全拍 {b["full"]:.4f} '
              f'ST-T {b["stt"]:.4f} T波 {b["tp"]:.3f} mV  |  '
              f'零相移参考 T波 {ctx["ref_tp"]:.3f}，温和链单独 T波 {ctx["g_tp"]:.3f}')

    cfgs = [('现状 不滤注入量', 0, False)]
    for k in (6, 7, 8, 9):
        cfgs.append((f'乙1 低通k={k} ({lp_fc(k):.2f}Hz) 检测也滤', k, True))
    for k in (7, 8):
        cfgs.append((f'乙2 低通k={k} ({lp_fc(k):.2f}Hz) 检测不滤', k, False))

    rows = []
    for name, k_lp, det in cfgs:
        rs = []
        for ctx in ctxs:
            y, d, w = build(ctx["raw"], k_lp, det)
            s = score(y, d, ctx)
            s["wm"] = w.mean()
            rs.append(s)
        rows.append(dict(
            name=name,
            full=min(r["full"] - c["base"]["full"] for r, c in zip(rs, ctxs)),
            p=min(r["p"] - c["base"]["p"] for r, c in zip(rs, ctxs)),
            stt=min(r["stt"] - c["base"]["stt"] for r, c in zip(rs, ctxs)),
            p2p=max((r["p2p"] - c["base"]["p2p"]) / c["base"]["p2p"] * 100
                    for r, c in zip(rs, ctxs)),
            bad=max(r["bad"] for r in rs),
            poll=max(r["poll"] for r in rs),
            tp=[r["tp"] for r in rs],
            wm=f'{rs[0]["wm"]:.3f}/{rs[1]["wm"]:.3f}',
            ab=[r["p2p"] for r in rs]))

    print('\n两段上的最差表现（Δ 相对定稿）')
    print('=' * 118)
    print(f'{"方案":<30}{"w均值":>13}{"d污染":>7}{"最差Δ全拍":>11}'
          f'{"最差ΔP段":>10}{"最差ΔST-T":>11}{"最差Δ漂移":>11}'
          f'{"T波mV":>13}{"错拍":>5}')
    print('-' * 118)
    for d in rows:
        tp = f'{d["tp"][0]:.3f}/{d["tp"][1]:.3f}'
        star = '  *' if (d["full"] > 0 and d["p"] > -0.01
                         and d["p2p"] < 0) else ''
        print(f'{d["name"]:<30}{d["wm"]:>13}{d["poll"]:>7.0f}'
              f'{d["full"]:>+11.4f}{d["p"]:>+10.4f}{d["stt"]:>+11.4f}'
              f'{d["p2p"]:>+11.1f}{tp:>13}{d["bad"]:>5}{star}')
    print('=' * 118)

    print('\nT 波峰值的参照（调参段/验证段）：')
    print(f'  零相移参考（上限）  {ctxs[0]["ref_tp"]:.3f} / {ctxs[1]["ref_tp"]:.3f} mV')
    print(f'  温和链单独          {ctxs[0]["g_tp"]:.3f} / {ctxs[1]["g_tp"]:.3f} mV')
    print(f'  定稿 LTI k7x2       {ctxs[0]["base"]["tp"]:.3f} / '
          f'{ctxs[1]["base"]["tp"]:.3f} mV')
    print('\n漂移绝对值（调参段/验证段，mV）：')
    for d in rows:
        print(f'  {d["name"]:<30} {d["ab"][0]:.3f} / {d["ab"][1]:.3f}')


if __name__ == '__main__':
    main()

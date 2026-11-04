# -*- coding: utf-8 -*-
"""
方案丙（等电位点锚）与方案丁（自残基线回减）-- 两条不用强链的路

方案丁（用户提出）：
    b_resid = 低通(y温和)        温和链输出里残留的基线
    y = y温和 - w * b_resid
w=1 时它等价于 (1-低通)*y温和，就是再加一级高通，仍在 LTI 曲线上；
w 可变才跳出去。结构优势：只有一条链、一个累加器，
不存在"两个基线估计各自漂走"的问题，合并稀释从根上没有。
硬件：一个低通累加器 + 一次乘法（量化成 2 的幂可省）。

方案丙（文献里的 cubic spline baseline removal）：
    只在基线**真正可观测**的地方取样 -- PR 段或 TP 段，每拍一个锚点，
    锚点之间插值，然后相减。
它不衰减任何频带，只去掉基线轨迹，原理上零相位失真。
代价：要先检测 R 波，且必须等到下一个锚点才能插值 -> 固有延迟约一个心拍。
本脚本用离线 R 波检测，相当于给出这条路的**上限**；
硬件实现要把这个延迟算进去。
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
    s = 1.0 / (1 << k)
    return signal.lfilter([s], [1.0, -(1.0 - s)], x)


def lp_fc(k):
    return FS / (2.0 * np.pi * (1 << k))


def plan_ding(x, k_lp, w_mode, p_lo=50, p_hi=99):
    """方案丁：自残基线回减。w_mode='fix1' 为 LTI 对照"""
    yg = gentle(x, K_G)
    lp = shift_lp(yg, k_lp)
    if w_mode == 'fix1':
        return yg - lp, np.ones(len(x))
    d = np.abs(lp)
    lo, hi = np.percentile(d, p_lo), np.percentile(d, p_hi)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg - w * lp, w


def plan_bing(x, seg, half_ms=20, kind='linear'):
    """方案丙：每拍取一个等电位锚点，插值成基线后相减

    seg='PR'  锚点取 R 峰前 80ms（P 波结束到 QRS 起点之间）
    seg='TP'  锚点取 R 峰后 520ms（T 波结束到下一个 P 之前）
    """
    yg = gentle(x, K_G)
    pk = hw.find_r_peaks(nl.full_chain(yg))
    off = int(-0.08 * FS) if seg == 'PR' else int(0.52 * FS)
    h = int(half_ms * FS / 1000)
    idx, val = [], []
    for p in pk:
        c = p + off
        a, b = c - h, c + h + 1
        if a < 0 or b > len(yg):
            continue
        idx.append(c)
        val.append(np.median(yg[a:b]))     # 中位数，抗单点离群
    if len(idx) < 4:
        return yg, 0
    idx = np.array(idx, dtype=float)
    val = np.array(val, dtype=float)
    t = np.arange(len(yg), dtype=float)
    if kind == 'cubic':
        from scipy.interpolate import CubicSpline
        base = CubicSpline(idx, val, extrapolate=True)(t)
    else:
        base = np.interp(t, idx, val)
    return yg - base, len(idx)


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
                p=c["P段"], stt=c["ST-T"], bad=ms + ex, tp=t_peak(out, pk))


def cur_dual(x):
    yg = gentle(x, 8)
    ya = aggr_gated(x, 6, 2, 400)
    d = np.abs(yg - ya)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg + w * (ya - yg)


def main():
    ctxs = []
    for nm, p in RECORDS:
        raw = load(p)
        ref = hw.chain_orig_zerophase(raw)
        ctx = dict(name=nm, raw=raw, ref=ref, peaks=hw.find_r_peaks(ref))
        ctx["base"] = score(hw.dc_block_cascade(raw, 7, 2), ctx)
        ctxs.append(ctx)
        b = ctx["base"]
        print(f'{nm}: {len(raw)} 点，参考 {len(ctx["peaks"])} 拍；'
              f'定稿基准 漂移 {b["p2p"]:.3f} 全拍 {b["full"]:.4f} '
              f'ST-T {b["stt"]:.4f} T波 {b["tp"]:.3f} mV')

    cfgs = [('参照 现状双链 k8+k6x2', lambda x: (cur_dual(x), None))]
    for k in (7, 8, 9):
        cfgs.append((f'丁 w=1 低通k={k} ({lp_fc(k):.2f}Hz) [LTI对照]',
                     lambda x, k=k: plan_ding(x, k, 'fix1')))
    for k in (7, 8, 9, 10):
        cfgs.append((f'丁 w可变 低通k={k} ({lp_fc(k):.2f}Hz)',
                     lambda x, k=k: plan_ding(x, k, 'var')))
    for seg in ('PR', 'TP'):
        for kind in ('linear', 'cubic'):
            cfgs.append((f'丙 锚点@{seg} {kind}',
                         lambda x, s=seg, kd=kind: plan_bing(x, s, kind=kd)))

    rows = []
    for name, fn in cfgs:
        rs = []
        for ctx in ctxs:
            y, _ = fn(ctx["raw"])
            rs.append(score(y, ctx))
        rows.append(dict(
            name=name,
            full=min(r["full"] - c["base"]["full"] for r, c in zip(rs, ctxs)),
            p=min(r["p"] - c["base"]["p"] for r, c in zip(rs, ctxs)),
            stt=min(r["stt"] - c["base"]["stt"] for r, c in zip(rs, ctxs)),
            p2p=max((r["p2p"] - c["base"]["p2p"]) / c["base"]["p2p"] * 100
                    for r, c in zip(rs, ctxs)),
            bad=max(r["bad"] for r in rs),
            tp=[r["tp"] for r in rs], ab=[r["p2p"] for r in rs]))

    print('\n两段上的最差表现（Δ 相对定稿）')
    print('=' * 112)
    print(f'{"方案":<34}{"最差Δ全拍":>11}{"最差ΔP段":>10}{"最差ΔST-T":>11}'
          f'{"最差Δ漂移":>11}{"T波mV":>13}{"漂移绝对":>14}{"错拍":>5}')
    print('-' * 112)
    for d in rows:
        star = '  *' if (d["full"] > 0 and d["p"] > -0.01
                         and d["p2p"] < 0) else ''
        print(f'{d["name"]:<34}{d["full"]:>+11.4f}{d["p"]:>+10.4f}'
              f'{d["stt"]:>+11.4f}{d["p2p"]:>+11.1f}'
              f'{f"{d[chr(39)+chr(39)] if False else d["tp"][0]:.3f}/{d["tp"][1]:.3f}":>13}'
              f'{f"{d["ab"][0]:.3f}/{d["ab"][1]:.3f}":>14}{d["bad"]:>5}{star}')
    print('=' * 112)

    win = [d for d in rows
           if d["full"] > 0 and d["p"] > -0.01 and d["p2p"] < 0]
    print(f'\n两段上同时「全拍更好 + P段不回退 + 漂移更小」：{len(win)} 个')
    for d in sorted(win, key=lambda z: z["p2p"]):
        print(f'  {d["name"]:<34} Δ全拍 {d["full"]:+.4f}  '
              f'Δ漂移 {d["p2p"]:+.1f}%  T波 {d["tp"][0]:.3f}/{d["tp"][1]:.3f}')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
方案甲：变时间常数单链 -- 把"需要合并"这件事本身消掉

双链合并的结构性毛病（用户指出）：
    y = x - [(1-w)*b温和 + w*b强]
w 大部分时间是 0.07~0.11 这种中间值，所以输出既不是温和链也不是
强阻断链，而是两者的加权平均 -- 劣势的平均，不是优势的并集。
更糟的是 (b强 - b温和) 里有 26~52% 是 T 波，正通过这个式子注进输出。

方案甲：只保留一条链，让它的更新速率随信号切换。
    acc += (x - acc) >> k_eff      k_eff 在 k_slow / k_fast 之间切
  · 任何时刻都是一种行为，不是混合 -> 优势不被稀释
  · 只有一个 acc 状态，改变速率不会让它跳变 -> 没有切换瞬态
  · 旋钮从 6 个降到 3~4 个

切换判据：输出里残留的慢分量。
    resid += (y - resid) >> k_resid
y = x - acc 就是输出，resid 就是"基线没被去干净的部分"。
它大，说明跟踪器落后了，该加快。带迟滞避免抖动。
硬件：多一个累加器、一个比较器、一个多路选择器，零乘法器。
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


def var_tc(x, k_slow, k_fast, stages, k_resid, thr_hi, thr_lo):
    """变时间常数单链；返回 (输出, 快速档比例, 切换次数, resid 序列)"""
    x = np.asarray(x, dtype=np.float64)
    s_slow, s_fast = 1.0 / (1 << k_slow), 1.0 / (1 << k_fast)
    s_r = 1.0 / (1 << k_resid)
    acc = np.zeros(stages)
    resid = 0.0
    fast = False
    n = len(x)
    y = np.empty(n)
    rs = np.empty(n)
    n_fast = 0
    n_sw = 0
    for i in range(n):
        s = s_fast if fast else s_slow
        n_fast += fast
        u = x[i]
        for j in range(stages):
            acc[j] += (u - acc[j]) * s
            u = u - acc[j]
        y[i] = u
        resid += (u - resid) * s_r
        rs[i] = resid
        a = abs(resid)
        if not fast and a > thr_hi:
            fast, n_sw = True, n_sw + 1
        elif fast and a < thr_lo:
            fast, n_sw = False, n_sw + 1
    return y, n_fast / n * 100, n_sw, rs


def calib(x, k_slow, stages, k_resid, p_hi, p_lo):
    """纯慢速档跑一遍，从 |resid| 的百分位定阈值 -- 换数据自动跟着走"""
    _, _, _, rs = var_tc(x, k_slow, k_slow, stages, k_resid, 1e18, -1.0)
    a = np.abs(rs)
    return np.percentile(a, p_hi), np.percentile(a, p_lo)


def score(y, ctx):
    out = nl.full_chain(y)
    pk = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ctx["ref"])
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    ms, ex = sw.match_peaks(pk, ctx["peaks"])[:2]
    return dict(p2p=(wd.max() - wd.min()) * LSB_MV, full=c["全拍"],
                p=c["P段"], stt=c["ST-T"], bad=ms + ex)


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


def best_dual(x):
    """联合扫描选出的最佳双链：温和 k8x1 + 强 k6x2 门控 thr=400"""
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
        ctx["dual"] = score(best_dual(raw), ctx)
        ctxs.append(ctx)
        b, d = ctx["base"], ctx["dual"]
        print(f'{nm}: 定稿 漂移 {b["p2p"]:.3f} 全拍 {b["full"]:.4f} '
              f'P {b["p"]:.4f} ST-T {b["stt"]:.4f}  |  '
              f'最佳双链 漂移 {d["p2p"]:.3f} 全拍 {d["full"]:.4f} '
              f'P {d["p"]:.4f} ST-T {d["stt"]:.4f}')

    rows = []
    for k_slow in (8, 9):
        for k_fast in (5, 6, 7):
            if k_fast >= k_slow:
                continue
            for stages in (1, 2):
                for p_hi, p_lo in ((80, 60), (90, 70), (95, 85)):
                    rs, fr, swn = [], [], []
                    for ctx in ctxs:
                        thi, tlo = calib(ctx["raw"], k_slow, stages, 10,
                                         p_hi, p_lo)
                        y, f, ns, _ = var_tc(ctx["raw"], k_slow, k_fast,
                                             stages, 10, thi, tlo)
                        rs.append(score(y, ctx))
                        fr.append(f)
                        swn.append(ns)
                    rows.append(dict(
                        name=f'k{k_slow}->k{k_fast} x{stages}级 p{p_hi}/{p_lo}',
                        full=min(r["full"] - c["base"]["full"]
                                 for r, c in zip(rs, ctxs)),
                        p=min(r["p"] - c["base"]["p"] for r, c in zip(rs, ctxs)),
                        stt=min(r["stt"] - c["base"]["stt"]
                                for r, c in zip(rs, ctxs)),
                        p2p=max((r["p2p"] - c["base"]["p2p"])
                                / c["base"]["p2p"] * 100
                                for r, c in zip(rs, ctxs)),
                        bad=max(r["bad"] for r in rs),
                        fr=f'{fr[0]:.0f}/{fr[1]:.0f}',
                        sw=f'{swn[0]}/{swn[1]}',
                        ab=[r["p2p"] for r in rs]))

    print('\n方案甲：各配置在两段上的最差表现（Δ 相对定稿）')
    print('=' * 112)
    print(f'{"配置":<26}{"快档%":>9}{"切换次数":>10}{"最差Δ全拍":>11}'
          f'{"最差ΔP段":>10}{"最差ΔST-T":>11}{"最差Δ漂移":>11}{"错拍":>5}')
    print('-' * 112)
    for d in sorted(rows, key=lambda z: -z["full"])[:14]:
        star = '  *' if (d["full"] > 0 and d["p"] > -0.01
                         and d["p2p"] < 0) else ''
        print(f'{d["name"]:<26}{d["fr"]:>9}{d["sw"]:>10}{d["full"]:>+11.4f}'
              f'{d["p"]:>+10.4f}{d["stt"]:>+11.4f}{d["p2p"]:>+11.1f}'
              f'{d["bad"]:>5}{star}')
    print('=' * 112)

    f = min(c["dual"]["full"] - c["base"]["full"] for c in ctxs)
    pp = min(c["dual"]["p"] - c["base"]["p"] for c in ctxs)
    st = min(c["dual"]["stt"] - c["base"]["stt"] for c in ctxs)
    w2 = max((c["dual"]["p2p"] - c["base"]["p2p"]) / c["base"]["p2p"] * 100
             for c in ctxs)
    print('\n对照：最佳双链（温和k8 + 强k6x2 thr=400）同口径')
    print(f'{"双链 k8+k6x2 thr=400":<26}{"-":>9}{"-":>10}{f:>+11.4f}'
          f'{pp:>+10.4f}{st:>+11.4f}{w2:>+11.1f}'
          f'{max(c["dual"]["bad"] for c in ctxs):>5}')

    win = [d for d in rows
           if d["full"] > 0 and d["p"] > -0.01 and d["p2p"] < 0]
    print(f'\n两段上同时「全拍更好 + P段不回退 + 漂移更小」：{len(win)} 个')
    for d in sorted(win, key=lambda z: z["p2p"])[:8]:
        print(f'  {d["name"]:<26} Δ全拍 {d["full"]:+.4f}  ΔP {d["p"]:+.4f}  '
              f'ΔST-T {d["stt"]:+.4f}  Δ漂移 {d["p2p"]:+.1f}%  '
              f'漂移绝对 {d["ab"][0]:.3f}/{d["ab"][1]:.3f} mV')


if __name__ == '__main__':
    main()

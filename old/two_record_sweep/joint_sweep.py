# -*- coding: utf-8 -*-
"""
双段联合扫描 —— 只认在两段实测数据上都站得住的配置

动机（cross_validate.py 查实）：在单段数据上扫出来的冠军
「温和k8 + 强k6×3级 + thr=400」换一段数据后，
漂移抑制从"好 27%"反转成"差 11%"，P 段还冒出 -0.067 的回退。
单段最优 ≠ 可用。

所以这里对每个配置在两段上都评一遍，记录**最差**的那一段的表现。
一个配置只有在两段上都不输给定稿，才算候选。

合格数据的筛选见会话记录：上位机四段自采数据里只有两段
采集端是调好的，另两段直流失调吃掉 46~52% 满量程、QRS 只有 0.1 mV。
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


def aggr(x, k, stages, gate):
    s = 1.0 / (1 << k)
    acc = np.zeros(stages)
    y = np.empty(len(x))
    for n in range(len(x)):
        u, g = x[n], gate[n]
        for j in range(stages):
            if not g:
                acc[j] += (u - acc[j]) * s
            u = u - acc[j]
        y[n] = u
    return y


def score(y, ctx):
    out = nl.full_chain(y)
    pk = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ctx['ref'])
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    ms, ex = sw.match_peaks(pk, ctx['peaks'])[:2]
    return dict(p2p=(wd.max() - wd.min()) * LSB_MV, full=c['全拍'],
                p=c['P段'], stt=c['ST-T'], bad=ms + ex)


def build(raw, k_g, k_a, st_a, thr):
    yg = gentle(raw, k_g)
    gate = (np.abs(np.diff(raw, prepend=raw[0])) >= thr if thr
            else np.zeros(len(raw), dtype=bool))
    ya = aggr(raw, k_a, st_a, gate)
    d = np.abs(yg - ya)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg + w * (ya - yg), gate.mean() * 100


ctxs = []
for nm, p in RECORDS:
    raw = load(p)
    ref = hw.chain_orig_zerophase(raw)
    ctx = dict(name=nm, raw=raw, ref=ref, peaks=hw.find_r_peaks(ref))
    ctx['base'] = score(hw.dc_block_cascade(raw, 7, 2), ctx)
    ctxs.append(ctx)
    b = ctx['base']
    print(f"{nm}：{len(raw)} 点，参考 {len(ctx['peaks'])} 拍，"
          f"定稿基准 漂移 {b['p2p']:.3f} mV 全拍 {b['full']:.4f} "
          f"P {b['p']:.4f} ST-T {b['stt']:.4f} 错拍 {b['bad']}")

rows = []
for k_g in (7, 8):
    for k_a in (6, 7, 8):
        for st_a in (2, 3, 4):
            for thr in (0, 400, 800, 1600):
                rs = []
                for ctx in ctxs:
                    y, fr = build(ctx['raw'], k_g, k_a, st_a, thr)
                    s = score(y, ctx)
                    s['fr'] = fr
                    rs.append(s)
                dfull = [r['full'] - c['base']['full'] for r, c in zip(rs, ctxs)]
                dp = [r['p'] - c['base']['p'] for r, c in zip(rs, ctxs)]
                dstt = [r['stt'] - c['base']['stt'] for r, c in zip(rs, ctxs)]
                dp2p = [(r['p2p'] - c['base']['p2p']) / c['base']['p2p'] * 100
                        for r, c in zip(rs, ctxs)]
                rows.append(dict(
                    name=f'k{k_g}+k{k_a}×{st_a} thr={thr}',
                    full=min(dfull), p=min(dp), stt=min(dstt),
                    p2p=max(dp2p), bad=max(r['bad'] for r in rs),
                    fr=f"{rs[0]['fr']:.0f}/{rs[1]['fr']:.0f}",
                    r=rs))

print('\n按"两段中最差的全拍改善"排序，全部 72 个配置的前 20：')
print('=' * 112)
print(f"{'配置':<22}{'冻结%':>9}{'最差Δ全拍':>11}{'最差ΔP段':>10}"
      f"{'最差ΔST-T':>11}{'最差Δ漂移':>11}{'调参段漂移':>11}{'验证段漂移':>11}{'错拍':>5}")
print(f"{'':<22}{'两段':>9}{'':>11}{'':>10}{'':>11}{'%':>11}"
      f"{'mV':>11}{'mV':>11}{'最多':>5}")
print('-' * 112)
for d in sorted(rows, key=lambda z: -z['full'])[:20]:
    mark = '  ★' if d['full'] > 0 and d['p'] > -0.01 and d['p2p'] < 0 else ''
    print(f"{d['name']:<22}{d['fr']:>9}{d['full']:>+11.4f}{d['p']:>+10.4f}"
          f"{d['stt']:>+11.4f}{d['p2p']:>+11.1f}"
          f"{d['r'][0]['p2p']:>11.3f}{d['r'][1]['p2p']:>11.3f}"
          f"{d['bad']:>5}{mark}")
print('=' * 112)

good = [d for d in rows if d['full'] > 0 and d['p'] > -0.01 and d['p2p'] < 0]
print(f"\n两段上同时做到「全拍更好 + P段不回退 + 漂移更小」的配置：{len(good)} 个")
for d in sorted(good, key=lambda z: z['p2p'])[:10]:
    print(f"  {d['name']:<22} Δ全拍 {d['full']:+.4f}  ΔP {d['p']:+.4f}  "
          f"ΔST-T {d['stt']:+.4f}  Δ漂移 {d['p2p']:+.1f}%  错拍 {d['bad']}")
if not good:
    print('  （无）—— 说明在这两段数据上，双链路换不来"两头都赢"')
    print('\n退一步：只要求全拍改善且漂移不劣化超过 10%：')
    soft = [d for d in rows if d['full'] > 0.02 and d['p2p'] < 10]
    for d in sorted(soft, key=lambda z: -z['full'])[:10]:
        print(f"  {d['name']:<22} Δ全拍 {d['full']:+.4f}  ΔP {d['p']:+.4f}  "
              f"ΔST-T {d['stt']:+.4f}  Δ漂移 {d['p2p']:+.1f}%  错拍 {d['bad']}")

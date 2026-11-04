# -*- coding: utf-8 -*-
"""
候选方案总表 -- 所有候选用同一套指标、同样两段数据重跑一遍

候选来自 8 轮结构试验（见 report/llm_log/）。这里不再探索，
只做最终对比，供定稿决策使用。

指标口径：
  漂移峰峰  直流阻断级输出在 0.05-0.5Hz 频带的峰峰值，越小越好
  四个相关  按 R 波对齐的平均心拍模板，与零相移参考比，分段算
            注意：相关系数做了 L2 归一化，对幅度是瞎的
  T波峰值   平均心拍里 T 波的绝对毫伏值 -- 相关系数看不到的那一维
  QRS/心率  最终交付量
  错拍      与零相移参考比对，漏检+多检
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


def shift_lp(x, k):
    s = 1.0 / (1 << k)
    return signal.lfilter([s], [1.0, -(1.0 - s)], x)


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


def c_lti(x):
    return hw.dc_block_cascade(x, 7, 2)


def c_gentle(x):
    return gentle(x, 8)


def c_dual(x, k_lp=0):
    yg = gentle(x, 8)
    ya = aggr_gated(x, 6, 2, 400)
    corr = ya - yg
    if k_lp:
        corr = shift_lp(corr, k_lp)
    d = np.abs(corr)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg + w * corr


def c_ding(x, k_lp):
    yg = gentle(x, 8)
    lp = shift_lp(yg, k_lp)
    d = np.abs(lp)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg - w * lp


def c_bing(x):
    yg = gentle(x, 8)
    pk = hw.find_r_peaks(nl.full_chain(yg))
    off, h = int(-0.08 * FS), int(0.02 * FS)
    idx, val = [], []
    for p in pk:
        c = p + off
        if c - h >= 0 and c + h + 1 <= len(yg):
            idx.append(c)
            val.append(np.median(yg[c - h:c + h + 1]))
    if len(idx) < 4:
        return yg
    return yg - np.interp(np.arange(len(yg), dtype=float),
                          np.array(idx, dtype=float), np.array(val))


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
                p=c["P段"], q=c["QRS"], stt=c["ST-T"], tp=t_peak(out, pk),
                qrs=hw.qrs_amplitude(out, pk) * LSB_MV,
                bpm=hw.heart_rate(pk), bad=ms + ex)


CANDS = [
    ('A  定稿 LTI k7x2级', c_lti),
    ('B  温和链单独 k8x1级', c_gentle),
    ('C  双链 k8+k6x2 thr400', lambda x: c_dual(x, 0)),
    ('D  双链+注入低通k=6', lambda x: c_dual(x, 6)),
    ('E  双链+注入低通k=7', lambda x: c_dual(x, 7)),
    ('F  单链自残回减 k=8', lambda x: c_ding(x, 8)),
    ('G  等电位锚点@PR', c_bing),
]

ctxs = []
for nm, p in RECORDS:
    raw = load(p)
    ref = hw.chain_orig_zerophase(raw)
    ctx = dict(name=nm, raw=raw, ref=ref, peaks=hw.find_r_peaks(ref))
    ctx["ref_tp"] = t_peak(ref, ctx["peaks"])
    ctx["ref_qrs"] = hw.qrs_amplitude(ref, ctx["peaks"]) * LSB_MV
    ctx["ref_bpm"] = hw.heart_rate(ctx["peaks"])
    ctxs.append(ctx)

res = {n: [f(c["raw"]) for c in ctxs] for n, f in CANDS}
sc = {n: [score(y, c) for y, c in zip(ys, ctxs)] for n, ys in res.items()}

for i, ctx in enumerate(ctxs):
    print(f'\n{"=" * 112}')
    print(f'### {ctx["name"]}   {len(ctx["raw"])} 点 / '
          f'{len(ctx["raw"])/FS:.1f} 秒，零相移参考：'
          f'{len(ctx["peaks"])} 拍，QRS {ctx["ref_qrs"]:.3f} mV，'
          f'T波 {ctx["ref_tp"]:.3f} mV，心率 {ctx["ref_bpm"]:.1f} BPM')
    print('=' * 112)
    print(f'{"候选":<24}{"漂移峰峰":>9}{"全拍":>8}{"P段":>8}{"QRS段":>8}'
          f'{"ST-T":>8}{"T波":>8}{"QRS":>8}{"心率":>8}{"错拍":>5}')
    print(f'{"":<24}{"mV":>9}{"相关":>8}{"相关":>8}{"相关":>8}'
          f'{"相关":>8}{"mV":>8}{"mV":>8}{"BPM":>8}{"个":>5}')
    print('-' * 112)
    for n, _ in CANDS:
        s = sc[n][i]
        print(f'{n:<24}{s["p2p"]:>9.3f}{s["full"]:>8.4f}{s["p"]:>8.4f}'
              f'{s["q"]:>8.4f}{s["stt"]:>8.4f}{s["tp"]:>8.3f}'
              f'{s["qrs"]:>8.3f}{s["bpm"]:>8.1f}{s["bad"]:>5}')

print(f'\n{"=" * 112}')
print('### 两段取最差 —— 这才是选型依据')
print('=' * 112)
print(f'{"候选":<24}{"最差漂移":>9}{"最差全拍":>9}{"最差P段":>9}'
      f'{"最差ST-T":>10}{"最差T波":>9}{"T波/参考":>10}{"最差错拍":>9}')
print('-' * 112)
for n, _ in CANDS:
    ss = sc[n]
    tr = min(s["tp"] / c["ref_tp"] for s, c in zip(ss, ctxs)) * 100
    print(f'{n:<24}{max(s["p2p"] for s in ss):>9.3f}'
          f'{min(s["full"] for s in ss):>9.4f}{min(s["p"] for s in ss):>9.4f}'
          f'{min(s["stt"] for s in ss):>10.4f}{min(s["tp"] for s in ss):>9.3f}'
          f'{tr:>9.0f}%{max(s["bad"] for s in ss):>9}')
print('=' * 112)

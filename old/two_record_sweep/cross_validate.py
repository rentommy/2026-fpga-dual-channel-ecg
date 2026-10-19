# -*- coding: utf-8 -*-
"""
换一段实测数据，看调出来的参数还成不成立

动机：现在这套非线性直流阻断有 6 个旋钮（温和链 k、强链 k、级数、
门控阈值、合并的 lo/hi 百分位），**全部**是在 ecg_60s_500sps.txt
这一条 60 秒记录上调出来的。而 gate_from_gentle.py 发现：
两个统计几乎一样的门控，漂移结果能差 80% —— 过拟合的征兆。

数据筛选（见会话记录）：上位机目录下四段自采数据里，
测试.txt 和 最佳片段.txt 来自采集端未调好的时期
（直流失调吃掉 46~52% 满量程、工频 46~57 µV、QRS 只有 0.1 mV），
不能用。只有 验证数据.txt 合格，复制为 ecg_val_60s_500sps.txt。

同时检验一件事：门控阈值写死 400 是这条记录的量纲，
换成"冻结比例"这种自适应口径是不是更可移植。
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
import gated_dual as gd               # noqa: E402

FS, LSB_MV = nl.FS, nl.LSB_MV
K_G, K_A, ST_A = 8, 6, 3              # sweep_aggressive.py 选出的工作点

RECORDS = [
    ('调参用 ecg_60s_500sps',
     os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')),
    ('验证用 ecg_val_60s_500sps',
     os.path.join(ROOT, 'data', 'source', 'ecg_val_60s_500sps.txt')),
]


def load(p):
    vals = []
    with open(p, encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                vals.append(int(line.strip()))
            except ValueError:
                pass
    return np.array(vals, dtype=np.float64)


def gentle(x, k):
    c = 1.0 - 1.0 / (1 << k)
    return signal.lfilter([c, -c], [1.0, -c], x)


def aggr_gated(x, k, stages, gate):
    x = np.asarray(x, dtype=np.float64)
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


def metrics(name, y, raw, ref, ref_peaks, extra=''):
    out = nl.full_chain(y)
    peaks = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ref)
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    miss, ext = sw.match_peaks(peaks, ref_peaks)[:2]
    return dict(name=name, p2p=(wd.max() - wd.min()) * LSB_MV,
                full=c['全拍'], p=c['P段'], qrs=c['QRS'], stt=c['ST-T'],
                miss=miss, extra=ext, note=extra)


def dual(raw, thr):
    """工作点：温和 k8×1 不门控 + 强 k6×3 门控，按 d 的 50/99 百分位渐变合并"""
    yg = gentle(raw, K_G)
    gate = np.abs(np.diff(raw, prepend=raw[0])) >= thr
    ya = aggr_gated(raw, K_A, ST_A, gate)
    d = np.abs(yg - ya)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return yg + w * (ya - yg), gate.mean() * 100


def table(rows, title):
    print(f'\n{title}')
    print('=' * 104)
    print(f"{'方案':<34}{'漂移峰峰':>9}{'全拍':>8}{'P段':>8}"
          f"{'QRS段':>8}{'ST-T':>8}{'漏/多':>7}{'备注':>14}")
    print('-' * 104)
    for d in rows:
        print(f"{d['name']:<34}{d['p2p']:>9.3f}{d['full']:>8.4f}"
              f"{d['p']:>8.4f}{d['qrs']:>8.4f}{d['stt']:>8.4f}"
              f"{str(d['miss'])+'/'+str(d['extra']):>7}{d['note']:>14}")
    print('=' * 104)


for title, path in RECORDS:
    raw = load(path)
    ref = hw.chain_orig_zerophase(raw)
    ref_peaks = hw.find_r_peaks(ref)
    dmag = np.abs(np.diff(raw, prepend=raw[0]))
    rows = []

    # 参照：当前定稿
    rows.append(metrics('定稿 LTI k=7×2级',
                        hw.dc_block_cascade(raw, 7, 2), raw, ref, ref_peaks))

    # 固定阈值（在调参记录上定的那个数）
    y, fr = dual(raw, 400)
    rows.append(metrics('双链 固定 thr=400', y, raw, ref, ref_peaks,
                        f'冻结 {fr:.1f}%'))

    # 自适应阈值：按目标冻结比例反推，换数据自动跟着走
    for target in (21, 10, 35):
        thr = np.percentile(dmag, 100 - target)
        y, fr = dual(raw, thr)
        rows.append(metrics(f'双链 自适应 冻结{target}%', y, raw, ref, ref_peaks,
                            f'thr={thr:.0f}'))

    print(f'\n### {title}  —  {len(raw)} 点 / {len(raw)/FS:.1f} 秒，'
          f'参考 {len(ref_peaks)} 拍，|Δx| 中位 {np.median(dmag):.0f} 码')
    table(rows, '')

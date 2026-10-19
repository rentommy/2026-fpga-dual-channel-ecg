# -*- coding: utf-8 -*-
"""
扫强阻断链的 k 和级数 —— 把拐点挪到 T 波频率之下

病因（slope_hold.py 查实）：强阻断链把 T 波当成基线减掉了 0.26 mV。
k=7 三级的合成拐点在 1.248 Hz，正落在 T 波的频率上。
这一件事同时造成 ST-T 相关下降和检测量 d 被污染。

所以扫 (k_a, 级数) 两个维度，看拐点挪到哪里最划算。
温和链固定 1 级，k_g 取 7 和 8 两种。

新增一个直接量病因的指标「吃掉T波」：
  把强阻断链减掉的基线按 R 波对齐平均，量 ST-T 段那个鼓包有多高。
  它越小，说明强阻断链越没动 T 波。
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
PRE, POST = int(0.3 * FS), int(0.5 * FS)
GATE_THR = 400


def dc_gated(x, k, stages, thr):
    """带门控的多级移位直流阻断，返回 (输出, 减掉的基线)"""
    x = np.asarray(x, dtype=np.float64)
    s = 1.0 / (1 << k)
    acc = np.zeros(stages)
    y = np.empty(len(x))
    prev = x[0]
    for n in range(len(x)):
        v = x[n]
        frozen = abs(v - prev) >= thr if thr else False
        prev = v
        u = v
        for j in range(stages):
            if not frozen:
                acc[j] += (u - acc[j]) * s
            u = u - acc[j]
        y[n] = u
    return y, x - y


def corner(k, st):
    """级联后的合成 -3dB 频率"""
    c = 1.0 - 1.0 / (1 << k)
    b, a = np.array([c, -c]), np.array([1.0, -c])
    lo, hi = 1e-4, 50.0
    for _ in range(120):
        mid = (lo + hi) / 2
        m = abs(signal.freqz(b, a, worN=[2 * np.pi * mid / FS])[1][0]) ** st
        if m < 0.70710678:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def t_wave_eaten(base, peaks):
    """强阻断链在 ST-T 段吃掉多少 T 波（按 R 波对齐平均后的鼓包高度，mV）"""
    segs = np.array([base[p - PRE:p + POST] for p in peaks
                     if p - PRE >= 0 and p + POST <= len(base)])
    if len(segs) < 5:
        return np.nan
    m = segs.mean(axis=0) * LSB_MV
    i0 = PRE + int(0.08 * FS)          # ST-T 段起点 +80 ms
    i1 = PRE + int(0.40 * FS)          # 终点 +400 ms
    return float(m[i0:i1].max() - m[PRE])


def one(raw, ref, ref_peaks, k_g, k_a, st_a):
    yg = hw.dc_block_cascade(raw, k_g, 1)          # 温和链：1 级，不门控
    ya, base = dc_gated(raw, k_a, st_a, GATE_THR)  # 强阻断链：门控
    d = np.abs(yg - ya)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    y = yg + w * (ya - yg)

    out = nl.full_chain(y)
    peaks = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ref)
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    miss, extra, _ = sw.match_peaks(peaks, ref_peaks)
    return dict(
        name=f'温和k{k_g} + 强k{k_a}×{st_a}级',
        fc=corner(k_a, st_a), eat=t_wave_eaten(base, peaks),
        poll=gd.pollution(d, peaks), wmean=w.mean(),
        p2p=(wd.max() - wd.min()) * LSB_MV,
        full=c['全拍'], p=c['P段'], qrs=c['QRS'], stt=c['ST-T'],
        miss=miss, extra=extra)


def table(rows, title):
    print(f'\n{title}')
    print('=' * 122)
    print(f"{'配置':<24}{'拐点':>7}{'吃T波':>8}{'d污染':>7}{'w均值':>7}"
          f"{'漂移峰峰':>9}{'全拍':>8}{'P段':>8}{'QRS段':>8}{'ST-T':>8}{'漏/多':>7}")
    print(f"{'':<24}{'Hz':>7}{'mV':>8}{'%':>7}{'':>7}"
          f"{'mV':>9}{'相关':>8}{'相关':>8}{'相关':>8}{'相关':>8}{'个':>7}")
    print('-' * 122)
    for d in rows:
        print(f"{d['name']:<24}{d['fc']:>7.3f}{d['eat']:>8.3f}{d['poll']:>7.0f}"
              f"{d['wmean']:>7.3f}{d['p2p']:>9.3f}{d['full']:>8.4f}"
              f"{d['p']:>8.4f}{d['qrs']:>8.4f}{d['stt']:>8.4f}"
              f"{str(d['miss'])+'/'+str(d['extra']):>7}")
    print('=' * 122)


def main():
    raw = nl.load()
    ref = hw.chain_orig_zerophase(raw)
    ref_peaks = hw.find_r_peaks(ref)
    print(f'实测数据 {len(raw)} 点，参考检出 {len(ref_peaks)} 拍')
    print(f'门控阈值固定 {GATE_THR}，温和链固定 1 级不门控\n')

    # 先给出纯 LTI 的两个参照，表里好对比
    for nm, st in (('定稿 LTI k=7×2级', 2),):
        y = hw.dc_block_cascade(raw, 7, st)
        out = nl.full_chain(y)
        c = nl.seg_corr(out, ref)
        wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
        pk = hw.find_r_peaks(out)
        ms, ex, _ = sw.match_peaks(pk, ref_peaks)
        print(f'【参照】{nm}：漂移峰峰 {(wd.max()-wd.min())*LSB_MV:.3f} mV，'
              f'全拍 {c["全拍"]:.4f}，P {c["P段"]:.4f}，'
              f'QRS {c["QRS"]:.4f}，ST-T {c["ST-T"]:.4f}，漏/多 {ms}/{ex}')

    for k_g in (7, 8):
        rows = [one(raw, ref, ref_peaks, k_g, k_a, st_a)
                for k_a in (6, 7, 8, 9) for st_a in (1, 2, 3, 4)]
        table(rows, f'温和链 k={k_g}，扫强阻断链：')

    print('\n读表提示：')
    print('  拐点  = 强阻断链级联后的合成 -3dB 频率，要低于 T 波内容才不吃它')
    print('  吃T波 = 强阻断链在 ST-T 段减掉的鼓包高度，直接量病因，越小越好')
    print('  w均值 = 强阻断链平均介入多少，拐点越低越弱，就得介入越多来补')


if __name__ == '__main__':
    main()

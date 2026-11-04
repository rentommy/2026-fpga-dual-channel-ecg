# -*- coding: utf-8 -*-
"""
门控的触发源：从原始数据换成温和链 —— 并做成真正的 R 波检测器

现状的问题（gated_dual.py / slope_hold.py 查实）：
  门控是 |x[n]-x[n-1]| >= 400 直接打在**原始数据**上。
  原始数据带着直流失调、漂移、50Hz 和宽带噪声，
  结果每拍触发约 54 次、平均每段 1.6 个点 —— 它在排除离群点，
  根本没有在"认 QRS"。

想法（用户提出）：
  温和链的输出是流水线里**当时最干净的信号**（直流已去、相位失真最小），
  用它来定位 R 波，再去门控强阻断链。

四种触发源一起比：
  A  |Δx|        原始数据上的瞬时斜率（现状）
  B  |Δy温和|    换成温和链，其余不变
  C  能量检测    Δy温和 → 平方 → 0.1s 滑动平均 → 自适应阈值（Pan-Tompkins 的套路）
  D  C + 窗口扩展  检测到之后，前后各罩住一段，把整个 QRS 包进去

D 需要主通路延迟，因为要先看到 QRS 才能罩住它的起点。
这个延迟是真实代价，表里标出来。
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
K_GENTLE, K_AGGR, ST_AGGR = 8, 6, 3          # sweep_aggressive.py 选出来的工作点


def dc_tf(k):
    """移位式直流阻断的等效传递函数，用 lfilter 跑比 Python 循环快得多"""
    c = 1.0 - 1.0 / (1 << k)
    return np.array([c, -c]), np.array([1.0, -c])


def gentle(x, k):
    return signal.lfilter(*dc_tf(k), x)


def aggr_gated(x, k, stages, gate):
    """强阻断链：gate 为 True 的采样点不更新基线"""
    x = np.asarray(x, dtype=np.float64)
    s = 1.0 / (1 << k)
    acc = np.zeros(stages)
    y = np.empty(len(x))
    for n in range(len(x)):
        u = x[n]
        g = gate[n]
        for j in range(stages):
            if not g:
                acc[j] += (u - acc[j]) * s
            u = u - acc[j]
        y[n] = u
    return y


# ── 四种触发源 ──
def gate_slope(sig, thr):
    """瞬时斜率阈值"""
    return np.abs(np.diff(sig, prepend=sig[0])) >= thr


def gate_energy(sig, frac=0.35, win_ms=100, pre=0, post=0):
    """
    Pan-Tompkins 式能量检测：微分 → 平方 → 滑动平均 → 自适应阈值

    frac     阈值取能量 98 百分位的多少倍（和 hw.find_r_peaks 同一套路）
    pre/post 检测到之后向前/向后各扩展多少点；pre>0 需要主通路延迟 pre 点
    """
    d = np.diff(sig, prepend=sig[0])
    e = d * d
    w = max(int(win_ms * FS / 1000), 1)
    e = np.convolve(e, np.ones(w) / w, mode='same')
    g = e > frac * np.percentile(e, 98)
    if pre or post:                       # 形态学膨胀，把窗口撑开
        k = np.ones(pre + post + 1)
        g = np.convolve(g.astype(float), k, mode='same') > 0
        if pre != post:                   # 不对称时 convolve 的中心要挪回来
            g = np.roll(g, (post - pre) // 2)
    return g


def gate_stats(gate, peaks):
    """冻结占比、每拍段数、以及冻结窗口相对 R 峰落在哪"""
    frac = gate.mean() * 100
    dd = np.diff(gate.astype(np.int8), prepend=0)
    nseg = int((dd == 1).sum())
    per_beat = nseg / max(len(peaks), 1)
    A, B = int(0.3 * FS), int(0.5 * FS)
    segs = np.array([gate[p - A:p + B] for p in peaks
                     if p - A >= 0 and p + B <= len(gate)])
    if len(segs) < 5:
        return frac, per_beat, np.nan, np.nan
    prof = segs.mean(axis=0)
    idx = np.where(prof > 0.5)[0]         # 半数以上心拍都冻结的区间
    if len(idx) == 0:
        return frac, per_beat, np.nan, np.nan
    return frac, per_beat, (idx[0] - A) / FS * 1000, (idx[-1] - A) / FS * 1000


def run(name, raw, ref, ref_peaks, gate, delay=0):
    yg = gentle(raw, K_GENTLE)
    ya = aggr_gated(raw, K_AGGR, ST_AGGR, gate)
    d = np.abs(yg - ya)
    lo, hi = np.percentile(d, 50), np.percentile(d, 99)
    w = np.clip((d - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    y = yg + w * (ya - yg)

    out = nl.full_chain(y)
    peaks = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ref)
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    miss, extra, _ = sw.match_peaks(peaks, ref_peaks)
    fr, pb, t0, t1 = gate_stats(gate, peaks)
    return dict(name=name, frac=fr, per_beat=pb, t0=t0, t1=t1, delay=delay,
                poll=gd.pollution(d, peaks),
                p2p=(wd.max() - wd.min()) * LSB_MV,
                full=c['全拍'], p=c['P段'], qrs=c['QRS'], stt=c['ST-T'],
                miss=miss, extra=extra)


def table(rows):
    print('=' * 128)
    print(f"{'触发源':<30}{'冻结':>6}{'每拍':>6}{'窗口相对R':>12}{'延迟':>6}"
          f"{'d污染':>7}{'漂移峰峰':>9}{'全拍':>8}{'ST-T':>8}{'漏/多':>7}")
    print(f"{'':<30}{'%':>6}{'段数':>6}{'ms':>12}{'点':>6}"
          f"{'%':>7}{'mV':>9}{'相关':>8}{'相关':>8}{'个':>7}")
    print('-' * 128)
    for d in rows:
        win = ('—' if np.isnan(d['t0'])
               else f"{d['t0']:+.0f}~{d['t1']:+.0f}")
        print(f"{d['name']:<30}{d['frac']:>6.1f}{d['per_beat']:>6.1f}"
              f"{win:>12}{d['delay']:>6d}{d['poll']:>7.0f}{d['p2p']:>9.3f}"
              f"{d['full']:>8.4f}{d['stt']:>8.4f}"
              f"{str(d['miss'])+'/'+str(d['extra']):>7}")
    print('=' * 128)


def main():
    raw = nl.load()
    ref = hw.chain_orig_zerophase(raw)
    ref_peaks = hw.find_r_peaks(ref)
    yg = gentle(raw, K_GENTLE)
    print(f'实测数据 {len(raw)} 点，参考检出 {len(ref_peaks)} 拍')
    print(f'工作点固定：温和 k={K_GENTLE}×1级，强阻断 k={K_AGGR}×{ST_AGGR}级\n')

    rows = [
        run('不门控', raw, ref, ref_peaks,
            np.zeros(len(raw), dtype=bool)),
        run('A 斜率@原始 thr=400', raw, ref, ref_peaks,
            gate_slope(raw, 400)),
        run('B 斜率@温和链 thr=400', raw, ref, ref_peaks,
            gate_slope(yg, 400)),
        run('B 斜率@温和链 thr=1000', raw, ref, ref_peaks,
            gate_slope(yg, 1000)),
    ]
    for frac in (0.20, 0.35, 0.60):
        rows.append(run(f'C 能量@温和链 frac={frac:g}', raw, ref, ref_peaks,
                        gate_energy(yg, frac=frac)))
    table(rows)

    print('\n窗口扩展（需要主通路延迟 pre 个点）：')
    rows2 = [run('C 能量 frac=0.35 不扩展', raw, ref, ref_peaks,
                 gate_energy(yg, frac=0.35))]
    for pre, post in ((10, 10), (25, 25), (25, 100), (25, 200)):
        rows2.append(run(f'D 扩展 前{pre}后{post}点', raw, ref, ref_peaks,
                         gate_energy(yg, frac=0.35, pre=pre, post=post),
                         delay=pre))
    table(rows2)

    print('\n读表提示：')
    print('  每拍段数 = 门控每个心拍触发多少次。真正在认 QRS 的话应该接近 1')
    print('  窗口相对R = 半数以上心拍都被冻结的时间区间，相对 R 波峰')
    print('  延迟 = 为了罩住 QRS 起点，主通路要多等多少点（FIR 已有 15 点）')


if __name__ == '__main__':
    main()

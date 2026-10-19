# -*- coding: utf-8 -*-
"""
门控期间：零阶保持 vs 斜率外推

问题（用户提出）：
  现在门控期间 acc 被冻成常数，而真实基线还在继续移动。
  门控一解除，acc 要用 2^k/fs ≈ 0.26 秒的时间常数去追赶 ——
  而这个追赶瞬态正好落在 ST-T 段上（R 峰后 80~400 ms）。
  这就是 gated_dual.py 里 ST-T 相关反而略降的原因。

想法：
  门控**之前**先测出 acc 的移动速率，门控期间按这个速率继续走，
  解除时 acc 已经在该在的位置附近，就不用追赶了。

  冻结（flat）：acc[n] = acc[n-1]           ← 错但安全
  外推（slope）：acc[n] = acc[n-1] + slope  ← 斜率对就赢，错了会跑飞

硬件代价：每级多一个斜率累加器（零乘法器）+ 门控期间一次加法。

斜率怎么来：正常更新时，delta = (u - acc) >> k 就是 acc 这一拍的增量，
把它过一级慢速低通就是速率估计，不需要额外求差。
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


def dual_slope(x, k_g, k_a, st_a, thr_lo, thr_hi, gate_thr,
               hold='flat', k_slope=5, clamp=0.0, w_levels=0):
    """
    温和链不门控；强阻断链门控，门控期间按 hold 指定的方式处理 acc

    hold='flat'   零阶保持（gated_dual.py 的做法）
    hold='slope'  按估计斜率外推
    k_slope       斜率估计的低通移位位数，越大越平滑越迟钝
    clamp         斜率绝对值上限（码/采样点），0 = 不限
    返回 (y, w, d, 冻结占比, 强阻断链总基线 base_a, 冻结标志)
    """
    x = np.asarray(x, dtype=np.float64)
    s_g, s_a = 1.0 / (1 << k_g), 1.0 / (1 << k_a)
    s_sl = 1.0 / (1 << k_slope)
    acc_g = 0.0
    acc_a = np.zeros(st_a)
    slope = np.zeros(st_a)
    n = len(x)
    y = np.empty(n)
    ws = np.empty(n)
    ds = np.empty(n)
    base = np.empty(n)          # 强阻断链一共减掉了多少，用来看追赶瞬态
    fz = np.zeros(n, dtype=bool)
    span = max(thr_hi - thr_lo, 1e-9)
    prev = x[0]
    n_frozen = 0

    for i in range(n):
        v = x[i]
        acc_g += (v - acc_g) * s_g
        g = v - acc_g

        frozen = abs(v - prev) >= gate_thr if gate_thr else False
        prev = v
        n_frozen += frozen
        fz[i] = frozen

        u = v
        for s in range(st_a):
            if frozen:
                if hold == 'slope':
                    acc_a[s] += slope[s]          # 按预测速率继续走
                # flat 模式什么都不做
            else:
                delta = (u - acc_a[s]) * s_a      # 这一拍 acc 的增量
                acc_a[s] += delta
                slope[s] += (delta - slope[s]) * s_sl   # 慢速跟踪速率
                if clamp:
                    slope[s] = max(-clamp, min(clamp, slope[s]))
            u = u - acc_a[s]
        a = u
        base[i] = v - a

        d = abs(g - a)
        w = (d - thr_lo) / span
        w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
        if w_levels:
            w = round(w * w_levels) / w_levels
        ds[i], ws[i] = d, w
        y[i] = g + w * (a - g)
    return y, ws, ds, n_frozen / n, base, fz


def runs(flag):
    """连续冻结段的长度统计 —— 外推风险和冻结时长直接相关"""
    d = np.diff(flag.astype(np.int8), prepend=0)
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    if len(ends) < len(starts):
        ends = np.append(ends, len(flag))
    L = ends - starts
    return (len(L), float(L.mean()), int(L.max())) if len(L) else (0, 0.0, 0)


def run(name, raw, ref, ref_peaks, **kw):
    y, ws, ds, frac, base, fz = dual_slope(raw, **kw)
    out = nl.full_chain(y)
    peaks = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ref)
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    miss, extra, _ = sw.match_peaks(peaks, ref_peaks)
    nr, lmean, lmax = runs(fz)
    return dict(name=name, poll=gd.pollution(ds, peaks), frozen=frac * 100,
                p2p=(wd.max() - wd.min()) * LSB_MV,
                full=c['全拍'], p=c['P段'], qrs=c['QRS'], stt=c['ST-T'],
                miss=miss, extra=extra, nr=nr, lmean=lmean, lmax=lmax,
                base=base, peaks=peaks)


def table(rows):
    print('=' * 112)
    print(f"{'方案':<30}{'d污染':>7}{'漂移峰峰':>9}{'全拍':>8}"
          f"{'P段':>8}{'QRS段':>8}{'ST-T':>8}{'漏/多':>7}{'冻结段':>8}{'最长':>6}")
    print(f"{'':<30}{'%':>7}{'mV':>9}{'相关':>8}"
          f"{'相关':>8}{'相关':>8}{'相关':>8}{'个':>7}{'均长点':>8}{'点':>6}")
    print('-' * 112)
    for d in rows:
        print(f"{d['name']:<30}{d['poll']:>7.0f}{d['p2p']:>9.3f}"
              f"{d['full']:>8.4f}{d['p']:>8.4f}{d['qrs']:>8.4f}{d['stt']:>8.4f}"
              f"{str(d['miss'])+'/'+str(d['extra']):>7}"
              f"{d['lmean']:>8.1f}{d['lmax']:>6d}")
    print('=' * 112)


def main():
    raw = nl.load()
    ref = hw.chain_orig_zerophase(raw)
    ref_peaks = hw.find_r_peaks(ref)
    yg = hw.dc_block_cascade(raw, 7, 1)
    ya = hw.dc_block_cascade(raw, 7, 2)
    dd = np.abs(yg - ya)
    lo50, lo99 = np.percentile(dd, 50), np.percentile(dd, 99)
    A = dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99, gate_thr=400)

    rows = [
        run('基准 不门控', raw, ref, ref_peaks,
            **{**A, 'gate_thr': 0}),
        run('门控 flat（当前）', raw, ref, ref_peaks, hold='flat', **A),
    ]
    for ks in (3, 5, 7, 9):
        rows.append(run(f'门控 slope k_slope={ks}', raw, ref, ref_peaks,
                        hold='slope', k_slope=ks, **A))
    table(rows)

    print('\n加斜率上限，防止长冻结时外推跑飞：')
    rows2 = [run('门控 flat（当前）', raw, ref, ref_peaks, hold='flat', **A)]
    for cl in (2.0, 5.0, 20.0):
        rows2.append(run(f'slope k=5 限幅 {cl:g} 码/点', raw, ref, ref_peaks,
                         hold='slope', k_slope=5, clamp=cl, **A))
    table(rows2)

    plot_catchup(rows[1], rows[3], ref_peaks)
    print(f"\n已画出追赶瞬态对比："
          f"{os.path.relpath(os.path.join(HERE, 'slope_catchup.png'), ROOT)}")


def plot_catchup(flat, slope, ref_peaks):
    """把强阻断链减掉的基线按 R 波对齐平均 —— 追赶瞬态在这里最清楚"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    A, B = int(0.3 * FS), int(0.5 * FS)
    t = np.arange(-A, B) / FS * 1000
    fig, ax = plt.subplots(figsize=(11, 5))
    for d, lab, c in ((flat, '零阶保持（冻成常数）', 'tab:red'),
                      (slope, '斜率外推', 'tab:green')):
        segs = np.array([d['base'][p - A:p + B] for p in d['peaks']
                         if p - A >= 0 and p + B <= len(d['base'])])
        m = segs.mean(axis=0) * LSB_MV
        ax.plot(t, m - m[0], lw=1.6, color=c, label=lab)
    ax.axvspan(-40, 40, color='gray', alpha=0.18, label='门控大致触发区')
    ax.axvspan(80, 400, color='orange', alpha=0.12, label='ST-T 段')
    ax.axvline(0, color='k', ls='--', lw=0.8)
    ax.set_xlabel('相对 R 波峰的时间 (ms)')
    ax.set_ylabel('强阻断链减掉的基线（相对拍首，mV）')
    ax.set_title('门控解除后的追赶瞬态：平的才对，拱起来就是在追赶')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, 'slope_catchup.png'), dpi=140)
    plt.close()


if __name__ == '__main__':
    main()

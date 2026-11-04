# -*- coding: utf-8 -*-
"""
双链路合并的切换瞬态检查 —— 渐变会不会在切换时产生伪迹

为什么必须单独查：形态指标是"按 R 波对齐叠加 74 拍再平均"算出来的，
短暂的切换伪迹在平均里会被摊薄，所以 nonlinear_dc.py 那张表
**抓不到这类问题**。必须直接看时域。

要回答四个问题：
  ① 权重 w 实际动得有多快
  ② 切换引入的输出跳变有多大，和信号自身的逐点变化相比是什么量级
  ③ 会不会造出假 R 峰，或者盖掉真 R 峰
  ④ 硬切换 / 渐变 / 限斜率 三种合并方式差多少

对照用的"信号自身逐点变化"是关键：如果切换跳变远小于信号本身
每个采样点的正常变化量，它就是看不见的。
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

import hw_filter_ref as hw        # noqa: E402
import nonlinear_dc as nl         # noqa: E402  （有 __main__ 保护，import 不会跑分析）

FS = nl.FS
LSB_MV = nl.LSB_MV
PEAK_TOL = int(0.05 * FS)         # R 峰匹配容差 ±50 ms


def dual_debug(x, k_g, k_a, st_a, thr_lo, thr_hi,
               mode='ramp', w_levels=0, max_dw=1.0):
    """
    双链路合并，额外返回 w 和两条链各自的输出，供瞬态分析

    mode='ramp'  线性渐变（nonlinear_dc.py 里用的那种）
    mode='hard'  硬切换，带迟滞：d>thr_hi 进，d<thr_lo 出
    max_dw       w 每个采样点最多允许变化多少（限斜率），1.0 = 不限
    """
    x = np.asarray(x, dtype=np.float64)
    s_g = 1.0 / (1 << k_g)
    s_a = 1.0 / (1 << k_a)
    acc_g = 0.0
    acc_a = np.zeros(st_a, dtype=np.float64)
    n = len(x)
    y = np.empty(n)
    yg = np.empty(n)
    ya = np.empty(n)
    ws = np.empty(n)
    span = max(thr_hi - thr_lo, 1e-9)
    w = 0.0
    state = 0                      # 仅 hard 模式用
    for i in range(n):
        v = x[i]
        acc_g += (v - acc_g) * s_g
        g = v - acc_g
        u = v
        for s in range(st_a):
            acc_a[s] += (u - acc_a[s]) * s_a
            u = u - acc_a[s]
        a = u
        d = abs(g - a)

        if mode == 'hard':
            if state == 0 and d > thr_hi:
                state = 1
            elif state == 1 and d < thr_lo:
                state = 0
            w_t = float(state)
        else:
            w_t = (d - thr_lo) / span
            w_t = 0.0 if w_t < 0.0 else (1.0 if w_t > 1.0 else w_t)
            if w_levels:
                w_t = round(w_t * w_levels) / w_levels

        dw = w_t - w                                  # 限斜率
        if dw > max_dw:
            w = w + max_dw
        elif dw < -max_dw:
            w = w - max_dw
        else:
            w = w_t

        yg[i], ya[i], ws[i] = g, a, w
        y[i] = g + w * (a - g)
    return y, ws, yg, ya


def match_peaks(cand, ref):
    """
    把候选 R 峰和参考 R 峰配对，先对齐整体延迟再匹配

    返回 (漏检数, 多检数, 位置误差中位数_ms)
    """
    if len(cand) == 0 or len(ref) == 0:
        return len(ref), len(cand), np.nan
    # 先估整体延迟：两条链群延迟不同，不对齐就全算成错配
    k = min(len(cand), len(ref))
    shift = int(np.median(cand[:k] - ref[:k]))
    c = cand - shift
    used = np.zeros(len(c), dtype=bool)
    errs = []
    miss = 0
    for r in ref:
        j = np.argmin(np.abs(c - r))
        if abs(c[j] - r) <= PEAK_TOL and not used[j]:
            used[j] = True
            errs.append(c[j] - r)
        else:
            miss += 1
    return miss, int((~used).sum()), \
        (float(np.median(np.abs(errs))) / FS * 1000 if errs else np.nan)


def analyse(name, raw, ref, ref_peaks, **kw):
    y, ws, yg, ya = dual_debug(raw, **kw)

    # ① w 动得有多快
    dw = np.abs(np.diff(ws, prepend=ws[0]))
    cross = int(np.sum((ws[:-1] < 0.5) != (ws[1:] < 0.5)))

    # ② 切换引入的跳变：Δw 乘上两条链当时的差
    #    必须掐掉前 2 秒：两条链的 acc 都从 0 起步，启动瞬态期间
    #    w 会被拉满，产生的跳变不是真正的切换行为（第一版就被它污染过）
    sk = 2 * FS
    jump = np.abs(dw * (ya - yg))[sk:] * LSB_MV
    # 对照：整条链输出自身的逐点变化（含滤波后，才是眼睛看到的）
    out = nl.full_chain(y)
    own = np.abs(np.diff(out, prepend=out[0]))[sk:] * LSB_MV

    # ③ R 峰有没有被影响
    miss, extra, perr = match_peaks(hw.find_r_peaks(out), ref_peaks)

    # ④ 质量指标，确认治瞬态没把前面的收益赔掉
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    p2p = (wd.max() - wd.min()) * LSB_MV
    c = nl.seg_corr(out, ref)

    return dict(
        name=name, w_mean=ws.mean(),
        pct0=float(np.mean(ws <= 1e-9) * 100),
        pct1=float(np.mean(ws >= 1 - 1e-9) * 100),
        cross=cross, max_dw=dw.max(),
        jump_999=float(np.percentile(jump, 99.9)), jump_max=jump.max(),
        own_999=float(np.percentile(own, 99.9)),
        miss=miss, extra=extra, perr=perr,
        p2p=p2p, full=c['全拍'], stt=c['ST-T'],
        worst=int(np.argmax(jump)) + sk,   # 加回偏移，指向原始下标
        y=y, ws=ws, yg=yg, ya=ya)


def main():
    raw = nl.load()
    ref = hw.chain_orig_zerophase(raw)
    ref_peaks = hw.find_r_peaks(ref)
    print(f'实测数据：{len(raw)} 点 = {len(raw)/FS:.1f} 秒，'
          f'参考检出 {len(ref_peaks)} 拍\n')

    yg0 = hw.dc_block_cascade(raw, 7, 1)
    ya0 = hw.dc_block_cascade(raw, 7, 2)
    dd = np.abs(yg0 - ya0)
    lo50, lo90, lo99 = (np.percentile(dd, q) for q in (50, 90, 99))

    cfgs = [
        # nonlinear_dc.py 里挑出来的两个工作点，原样复查
        ('① 双链 k7+k7×3 中→高 渐变',
         dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99, mode='ramp')),
        ('② 双链 k8+k7×2 高→满 渐变',
         dict(k_g=8, k_a=7, st_a=2, thr_lo=lo90, thr_hi=lo99, mode='ramp')),
        # 对照：硬切换，看渐变到底有没有必要
        ('③ 同① 但硬切换+迟滞',
         dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99, mode='hard')),
        ('④ 同② 但硬切换+迟滞',
         dict(k_g=8, k_a=7, st_a=2, thr_lo=lo90, thr_hi=lo99, mode='hard')),
        # 对照：渐变 + 限斜率，w 每点最多动 1/256
        ('⑤ 同① 加限斜率 1/256',
         dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99,
              mode='ramp', max_dw=1.0 / 256)),
        # 零乘法器版本也查一遍，量化会让 w 阶梯式跳动
        ('⑥ 同① 权重8档（零乘法器）',
         dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99,
              mode='ramp', w_levels=8)),
        ('⑦ 同⑥ 再加限斜率 1/256',
         dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99,
              mode='ramp', w_levels=8, max_dw=1.0 / 256)),
    ]

    rows = [analyse(n, raw, ref, ref_peaks, **kw) for n, kw in cfgs]

    print('【权重 w 的行为】')
    print('-' * 86)
    print(f"{'方案':<26}{'均值':>7}{'w=0占比':>9}{'w=1占比':>9}"
          f"{'过0.5次数':>10}{'单点最大Δw':>12}")
    print('-' * 86)
    for d in rows:
        print(f"{d['name']:<26}{d['w_mean']:>7.3f}{d['pct0']:>9.1f}"
              f"{d['pct1']:>9.1f}{d['cross']:>10d}{d['max_dw']:>12.4f}")

    print('\n【切换引入的跳变 vs 信号自身的逐点变化】（mV）')
    print('-' * 86)
    print(f"{'方案':<26}{'跳变99.9%':>11}{'跳变最大':>10}"
          f"{'自身99.9%':>11}{'占比':>8}")
    print('-' * 86)
    for d in rows:
        r = d['jump_max'] / d['own_999'] * 100
        print(f"{d['name']:<26}{d['jump_999']:>11.4f}{d['jump_max']:>10.4f}"
              f"{d['own_999']:>11.4f}{r:>7.1f}%")

    print('\n【R 峰检测与质量指标】')
    print('-' * 96)
    print(f"{'方案':<26}{'漏检':>5}{'多检':>5}{'位置误差':>9}"
          f"{'漂移峰峰':>10}{'全拍':>8}{'ST-T':>8}")
    print(f"{'':<26}{'个':>5}{'个':>5}{'ms':>9}{'mV':>10}{'相关':>8}{'相关':>8}")
    print('-' * 96)
    for d in rows:
        print(f"{d['name']:<26}{d['miss']:>5d}{d['extra']:>5d}"
              f"{d['perr']:>9.1f}{d['p2p']:>10.3f}"
              f"{d['full']:>8.4f}{d['stt']:>8.4f}")

    # 把最坏那一刻的波形画出来，平均模板看不到的东西只能这样看
    plot_worst(rows[0], raw)
    print(f"\n已画出 ① 最坏切换时刻的波形："
          f"{os.path.relpath(os.path.join(HERE, 'switch_worst.png'), ROOT)}")


def plot_worst(d, raw):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    c = d['worst']
    a, b = max(0, c - 2 * FS), min(len(raw), c + 2 * FS)
    t = np.arange(a, b) / FS
    fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                           gridspec_kw={'height_ratios': [3, 1]})
    ax[0].plot(t, d['yg'][a:b] * LSB_MV, lw=0.9, alpha=0.65, label='温和链 1 级')
    ax[0].plot(t, d['ya'][a:b] * LSB_MV, lw=0.9, alpha=0.65, label='强阻断链 3 级')
    ax[0].plot(t, d['y'][a:b] * LSB_MV, 'k', lw=1.3, label='合并输出')
    ax[0].axvline(c / FS, color='r', ls='--', lw=0.8, label='最大跳变处')
    ax[0].set_ylabel('mV')
    ax[0].set_title('双链路合并：最坏切换时刻前后 ±2 秒（直流阻断级输出）')
    ax[0].legend(loc='upper right', fontsize=9)
    ax[0].grid(alpha=0.3)
    ax[1].plot(t, d['ws'][a:b], 'g', lw=1.1)
    ax[1].set_ylabel('权重 w')
    ax[1].set_xlabel('时间 (s)')
    ax[1].set_ylim(-0.05, 1.05)
    ax[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, 'switch_worst.png'), dpi=140)
    plt.close()


if __name__ == '__main__':
    main()

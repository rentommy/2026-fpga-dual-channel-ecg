# -*- coding: utf-8 -*-
"""
非线性直流阻断的两个试验 —— 跳出 LTI 取舍边界

背景：k 和级数构成的 LTI 空间里，"压漂移"和"低相位失真"严格单调对立，
不存在两头都好的点（见 report/llm_log/2026-10-18.md）。
出路是让滤波行为**依赖信号本身**，也就是非线性/时变。

本文件实现两个方案：

  方案②  QRS 期间冻结基线更新
          acc 是基线估计，QRS 那个大尖峰会把它拽起来，拽完在 QRS 后
          形成下冲、压低 ST 段。检测到大斜率就暂停 acc 更新，
          让基线估计不被心跳本身污染。
          硬件代价：一个比较器 + 一个条件。零乘法器。

  方案①  双链路 + 信号相关的渐变合并
          温和链（1 级）保形态，强阻断链（2/3 级）压漂移。
          两条链输出之差恰好等于两个基线估计之差：
              y_gentle - y_aggr = (x-acc1) - (x-acc2) = acc2 - acc1
          所以实现上不必真算两条链，只要：
              y = y_gentle - w · (acc2 - acc1)
          w 由 |acc2-acc1| 决定 —— 两个估计吵得厉害，说明正在发生
          大幅摆动，这时才让强阻断介入。
          硬件代价：多一个 acc（零乘法器）+ 一次乘法；
          w 量化成 2 的幂次的话连那次乘法也省掉。

评价指标刻意不用模型判读。原因：那个模型是用 filtfilt 数据训练的，
拿它比较因果链和零相移链是循环论证 —— 零相移方是域内数据，必然赢。
这里改用**分波段的心拍形态相关**，能定位失真具体落在哪一段。
"""
import os
import sys

import numpy as np
from scipy import signal

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))   # 工程根目录 ecg_fpga/
sys.path.insert(0, os.path.join(ROOT, 'src', 'ps'))

import hw_filter_ref as hw   # noqa: E402

RAW = os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')
FS = hw.FS
LSB_MV = hw.LSB_UV / 1000.0
WANDER_SOS = signal.butter(4, [0.05, 0.5], btype='bandpass',
                           fs=FS, output='sos')

# 心拍分段窗口（相对 R 波峰，单位 ms）
SEGMENTS = {
    'P段': (-250, -80),      # 低频小幅，对相位失真最敏感
    'QRS': (-80, 80),        # 高频大幅，相位失真影响最小
    'ST-T': (80, 400),       # 低频中幅，有临床含义
}
TPL_PRE, TPL_POST = -250, 400


# ══════════════════════════════════════════════════════════════════
#  方案②：QRS 期间冻结基线更新
# ══════════════════════════════════════════════════════════════════
def dc_block_gated(x, k, stages, thr):
    """
    带 QRS 门控的移位式直流阻断

    thr 的单位是"码/采样点"（相邻样本差的绝对值）。
    漂移斜率约 13 码/点，QRS 上升支约 1000 码/点以上，
    中间有两个数量级的空档，阈值不敏感。
    """
    x = np.asarray(x, dtype=np.float64)
    step = 1.0 / (1 << k)
    acc = np.zeros(stages, dtype=np.float64)
    y = np.empty(len(x), dtype=np.float64)
    prev = x[0]
    n_frozen = 0
    for n in range(len(x)):
        v = x[n]
        gate = abs(v - prev) < thr        # True = 平静期，允许更新基线
        n_frozen += (not gate)
        prev = v
        for s in range(stages):
            if gate:
                acc[s] += (v - acc[s]) * step
            v = v - acc[s]
        y[n] = v
    return y, n_frozen / len(x)


# ══════════════════════════════════════════════════════════════════
#  方案①：双链路 + 信号相关的渐变合并
# ══════════════════════════════════════════════════════════════════
def dc_block_dual(x, k_gentle, k_aggr, stages_aggr,
                  thr_lo, thr_hi, w_levels=0):
    """
    温和链 1 级 + 强阻断链 stages_aggr 级，按两者基线估计之差渐变合并

    w_levels=0  连续权重（上限参考，硬件要一次乘法）
    w_levels=N  权重量化成 N 档（硬件可用移位+累加实现，零乘法器）

    返回 (y, w_mean, w_max)
    """
    x = np.asarray(x, dtype=np.float64)
    s_g = 1.0 / (1 << k_gentle)
    s_a = 1.0 / (1 << k_aggr)
    acc_g = 0.0
    acc_a = np.zeros(stages_aggr, dtype=np.float64)
    y = np.empty(len(x), dtype=np.float64)
    ws = np.empty(len(x), dtype=np.float64)
    span = max(thr_hi - thr_lo, 1e-9)
    for n in range(len(x)):
        v = x[n]
        # 温和链：1 级
        acc_g += (v - acc_g) * s_g
        y_g = v - acc_g
        # 强阻断链：stages_aggr 级，自己独立的一串 acc
        u = v
        for s in range(stages_aggr):
            acc_a[s] += (u - acc_a[s]) * s_a
            u = u - acc_a[s]
        y_a = u
        # 两条链吵得多厉害 → 决定强阻断介入多少
        d = abs(y_g - y_a)
        w = (d - thr_lo) / span
        w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
        if w_levels:
            w = round(w * w_levels) / w_levels
        ws[n] = w
        y[n] = y_g + w * (y_a - y_g)
    return y, ws.mean(), ws.max()


# ══════════════════════════════════════════════════════════════════
#  评价：分波段心拍形态相关
# ══════════════════════════════════════════════════════════════════
def beat_template(x):
    """按 R 波对齐叠加出平均心拍，返回未归一化的模板"""
    peaks = hw.find_r_peaks(x, FS)
    a = int(-TPL_PRE * FS / 1000)
    b = int(TPL_POST * FS / 1000)
    segs = [x[p - a:p + b] for p in peaks
            if p - a >= 0 and p + b <= len(x)]
    return None if len(segs) < 5 else np.mean(np.array(segs), axis=0)


def _norm(v):
    v = v - v.mean()
    return v / (np.linalg.norm(v) + 1e-12)


def seg_corr(y, ref):
    """整拍 + 三个波段分别的形态相关系数"""
    ty, tr = beat_template(y), beat_template(ref)
    if ty is None or tr is None:
        return {k: np.nan for k in ['全拍'] + list(SEGMENTS)}
    out = {'全拍': float(np.dot(_norm(ty), _norm(tr)))}
    off = int(-TPL_PRE * FS / 1000)
    for name, (t0, t1) in SEGMENTS.items():
        i0 = off + int(t0 * FS / 1000)
        i1 = off + int(t1 * FS / 1000)
        out[name] = float(np.dot(_norm(ty[i0:i1]), _norm(tr[i0:i1])))
    return out


def full_chain(dc_out):
    """直流阻断之后的两级固定不变：陷波 Q=15 + 31 抽头 FIR"""
    y = hw.notch_apply(dc_out, *hw.notch_coef(50.0, 15.0, FS))
    return hw.fir_apply(y, hw.fir_lowpass(31, 40.0, FS))


def evaluate(name, dc_out, ref, extra=''):
    y = full_chain(dc_out)
    w = signal.sosfiltfilt(WANDER_SOS, dc_out)
    p2p = (w.max() - w.min()) * LSB_MV
    peaks = hw.find_r_peaks(y)
    qrs = hw.qrs_amplitude(y, peaks) * LSB_MV
    c = seg_corr(y, ref)
    return dict(name=name, p2p=p2p, ratio=p2p / qrs * 100, qrs=qrs,
                n_beat=len(peaks), bpm=hw.heart_rate(peaks),
                extra=extra, **c)


def load():
    vals = []
    with open(RAW, encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                vals.append(int(line.strip()))
            except ValueError:
                pass
    return np.array(vals, dtype=np.float64)


def table(rows, title):
    print(f'\n{title}')
    print('=' * 112)
    print(f"{'方案':<30}{'漂移峰峰':>9}{'/QRS':>7}{'QRS':>8}"
          f"{'全拍':>8}{'P段':>8}{'QRS段':>8}{'ST-T':>8}{'心拍':>5}")
    print(f"{'':<30}{'mV':>9}{'%':>7}{'mV':>8}"
          f"{'相关':>8}{'相关':>8}{'相关':>8}{'相关':>8}{'个':>5}")
    print('-' * 112)
    for d in rows:
        print(f"{d['name']:<30}{d['p2p']:>9.3f}{d['ratio']:>7.0f}"
              f"{d['qrs']:>8.3f}{d['全拍']:>8.4f}{d['P段']:>8.4f}"
              f"{d['QRS']:>8.4f}{d['ST-T']:>8.4f}{d['n_beat']:>5d}")
    print('=' * 112)
    for d in rows:
        if d['extra']:
            print(f"  {d['name']}：{d['extra']}")


def main():
    raw = load()
    print(f'实测数据：{len(raw)} 点 = {len(raw)/FS:.1f} 秒')
    ref = hw.chain_orig_zerophase(raw)          # 零相移参考，形态的上限

    # 门控阈值要选在"漂移斜率"和"QRS 斜率"之间，先把分布摆出来
    d1 = np.abs(np.diff(raw))
    print('\n相邻样本差 |x[n]-x[n-1]| 的分布（码）：')
    for q in (50, 90, 99, 99.5, 99.9):
        print(f'  {q:>5.1f} 百分位 {np.percentile(d1, q):>8.0f}')
    print(f'  {"最大":>8} {d1.max():>8.0f}')

    # ── 基准线：现有的 LTI 方案 ──
    base = [
        evaluate('LTI k=7 ×1级', hw.dc_block_cascade(raw, 7, 1), ref,
                 '形态最好，但漂移压不住'),
        evaluate('LTI k=7 ×2级（当前定稿）', hw.dc_block_cascade(raw, 7, 2), ref,
                 '当前定稿'),
        evaluate('LTI k=7 ×3级', hw.dc_block_cascade(raw, 7, 3), ref,
                 '漂移最好，但形态崩'),
    ]
    table(base, '【基准】现有 LTI 方案')

    # ── 方案②：QRS 门控 ──
    g = []
    for st in (1, 2):
        for thr in (100, 200, 400, 800):
            y, frac = dc_block_gated(raw, 7, st, thr)
            g.append(evaluate(f'② 门控 k=7 ×{st}级 thr={thr}', y, ref,
                              f'冻结占比 {frac*100:.1f}%'))
    table(g, '【方案②】QRS 期间冻结基线更新')

    # ── 方案①：双链路渐变合并 ──
    # 阈值从"两条链输出之差"的分布里取
    yg = hw.dc_block_cascade(raw, 7, 1)
    ya = hw.dc_block_cascade(raw, 7, 2)
    dd = np.abs(yg - ya)
    print('\n温和链与强阻断链输出之差 |y1-y2| 的分布（码）：')
    for q in (50, 75, 90, 99):
        print(f'  {q:>5.1f} 百分位 {np.percentile(dd, q):>8.0f}')
    lo50, lo90, lo99 = (np.percentile(dd, q) for q in (50, 90, 99))

    d_rows = []
    for kg, ka, sa in ((7, 7, 2), (8, 7, 2), (7, 7, 3)):
        for tag, (t0, t1) in (('中→高', (lo50, lo99)),
                              ('高→满', (lo90, lo99))):
            y, wm, wx = dc_block_dual(raw, kg, ka, sa, t0, t1)
            d_rows.append(evaluate(
                f'① 双链 k{kg}+k{ka}×{sa} {tag}', y, ref,
                f'权重均值 {wm:.3f} 峰值 {wx:.3f}（连续）'))
    # 权重量化成 8 档，验证能不能省掉那次乘法
    y, wm, wx = dc_block_dual(raw, 7, 7, 2, lo50, lo99, w_levels=8)
    d_rows.append(evaluate('① 双链 k7+k7×2 权重8档', y, ref,
                           f'权重均值 {wm:.3f}（量化，零乘法器）'))
    table(d_rows, '【方案①】双链路 + 信号相关渐变合并')

    print('\n读表提示：')
    print('  · 漂移峰峰越小越好；四个相关系数越接近 1 越好')
    print('  · 按机理预测：相位失真伤低频，所以 P段 和 ST-T 应该比 QRS段 掉得多')
    print('  · 方案②针对 ST-T；方案①针对整体')


if __name__ == '__main__':
    main()

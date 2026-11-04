# -*- coding: utf-8 -*-
"""
双链路 + 只在强阻断链上加门控 —— 治病因而不是治症状

思路（用户提出）：
  检测量 d 被心跳污染，根源是**强阻断链把心跳本身也削掉了一部分**，
  于是两条链在每个心拍上都要吵一次。
  那么与其事后把 d 滤平（治症状），不如让强阻断链**在心拍期间
  别动它的基线估计**（治病因）——心跳不进基线估计，两条链就不吵了。

  温和链不门控：它的任务就是保形态，本来就没削心跳。

两种门控形状：
  'deriv'  瞬时斜率门控：|x[n]-x[n-1]| > thr 就冻结
           只认 QRS 那个陡边，T 波是慢的，认不出来
  'hold'   触发后保持：QRS 触发一次，接着再冻结 hold 个点
           目的是把 ST-T 段也罩进去，覆盖真正的污染源

要同时回答两件事：
  ① 最终效果（漂移 / 形态 / R 峰）有没有改善
  ② 检测量 d 的心跳污染有没有下降
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
import switch_transient as st         # noqa: E402

FS, LSB_MV = nl.FS, nl.LSB_MV
PRE, POST = int(0.3 * FS), int(0.5 * FS)      # 污染度量窗口：R 峰前 300 后 500 ms


def dual_gated(x, k_g, k_a, st_a, thr_lo, thr_hi,
               gate_thr=0, gate_mode='deriv', hold=0, w_levels=0):
    """
    温和链 1 级（不门控） + 强阻断链 st_a 级（可门控），渐变合并

    gate_thr=0 → 不门控，退化成 nonlinear_dc.dc_block_dual
    返回 (y, w, d, 冻结占比)
    """
    x = np.asarray(x, dtype=np.float64)
    s_g, s_a = 1.0 / (1 << k_g), 1.0 / (1 << k_a)
    acc_g = 0.0
    acc_a = np.zeros(st_a, dtype=np.float64)
    n = len(x)
    y = np.empty(n)
    ws = np.empty(n)
    ds = np.empty(n)
    span = max(thr_hi - thr_lo, 1e-9)
    prev = x[0]
    hold_cnt = 0
    n_frozen = 0

    for i in range(n):
        v = x[i]
        # ── 温和链：永远更新 ──
        acc_g += (v - acc_g) * s_g
        g = v - acc_g

        # ── 门控判定 ──
        if gate_thr:
            trig = abs(v - prev) >= gate_thr
            if gate_mode == 'hold':
                if trig:
                    hold_cnt = hold
                elif hold_cnt > 0:
                    hold_cnt -= 1
                frozen = trig or hold_cnt > 0
            else:
                frozen = trig
        else:
            frozen = False
        prev = v
        n_frozen += frozen

        # ── 强阻断链：冻结时只做减法，不更新基线 ──
        u = v
        for s in range(st_a):
            if not frozen:
                acc_a[s] += (u - acc_a[s]) * s_a
            u = u - acc_a[s]
        a = u

        d = abs(g - a)
        w = (d - thr_lo) / span
        w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
        if w_levels:
            w = round(w * w_levels) / w_levels
        ds[i], ws[i] = d, w
        y[i] = g + w * (a - g)
    return y, ws, ds, n_frozen / n


def pollution(d, peaks):
    """检测量在一拍之内被顶起多少，占它自身典型值的百分比"""
    segs = np.array([d[p - PRE:p + POST] for p in peaks
                     if p - PRE >= 0 and p + POST <= len(d)])
    if len(segs) < 5:
        return np.nan
    m = segs.mean(axis=0)
    return float((m.max() - m.min()) / np.median(d) * 100)


def run(name, raw, ref, ref_peaks, **kw):
    y, ws, ds, frac = dual_gated(raw, **kw)
    out = nl.full_chain(y)
    peaks = hw.find_r_peaks(out)
    c = nl.seg_corr(out, ref)
    wd = signal.sosfiltfilt(nl.WANDER_SOS, y)
    miss, extra, perr = st.match_peaks(peaks, ref_peaks)
    sk = 2 * FS
    dw = np.abs(np.diff(ws, prepend=ws[0]))
    jump = np.abs(dw * ds)[sk:] * LSB_MV           # d 就是两链之差，正好是跳变幅度
    own = np.abs(np.diff(out, prepend=out[0]))[sk:] * LSB_MV
    return dict(
        name=name, poll=pollution(ds, peaks), frozen=frac * 100,
        p2p=(wd.max() - wd.min()) * LSB_MV,
        full=c['全拍'], p=c['P段'], qrs=c['QRS'], stt=c['ST-T'],
        miss=miss, extra=extra,
        jump=jump.max() / np.percentile(own, 99.9) * 100,
        w_mean=ws.mean())


def table(rows):
    print('=' * 118)
    print(f"{'方案':<30}{'d污染':>7}{'冻结':>7}{'漂移峰峰':>9}"
          f"{'全拍':>8}{'P段':>8}{'QRS段':>8}{'ST-T':>8}"
          f"{'漏/多':>7}{'跳变':>7}")
    print(f"{'':<30}{'%':>7}{'%':>7}{'mV':>9}"
          f"{'相关':>8}{'相关':>8}{'相关':>8}{'相关':>8}{'个':>7}{'%':>7}")
    print('-' * 118)
    for d in rows:
        print(f"{d['name']:<30}{d['poll']:>7.0f}{d['frozen']:>7.1f}"
              f"{d['p2p']:>9.3f}{d['full']:>8.4f}{d['p']:>8.4f}"
              f"{d['qrs']:>8.4f}{d['stt']:>8.4f}"
              f"{str(d['miss'])+'/'+str(d['extra']):>7}{d['jump']:>7.1f}")
    print('=' * 118)


def main():
    raw = nl.load()
    ref = hw.chain_orig_zerophase(raw)
    ref_peaks = hw.find_r_peaks(ref)
    print(f'实测数据 {len(raw)} 点，参考检出 {len(ref_peaks)} 拍\n')

    yg = hw.dc_block_cascade(raw, 7, 1)
    ya = hw.dc_block_cascade(raw, 7, 2)
    dd = np.abs(yg - ya)
    lo50, lo90, lo99 = (np.percentile(dd, q) for q in (50, 90, 99))

    A = dict(k_g=7, k_a=7, st_a=3, thr_lo=lo50, thr_hi=lo99)   # 工作点①
    B = dict(k_g=8, k_a=7, st_a=2, thr_lo=lo90, thr_hi=lo99)   # 工作点②

    rows = [run('① 双链 k7+k7×3（不门控）', raw, ref, ref_peaks, **A)]
    for thr in (400, 800, 1600, 3000):
        rows.append(run(f'①+门控 deriv thr={thr}', raw, ref, ref_peaks,
                        gate_thr=thr, gate_mode='deriv', **A))
    for hold in (40, 100, 200):
        rows.append(run(f'①+门控 hold={hold}点 thr=800', raw, ref, ref_peaks,
                        gate_thr=800, gate_mode='hold', hold=hold, **A))
    table(rows)

    print('\n工作点② 上重复一遍：')
    rows2 = [run('② 双链 k8+k7×2（不门控）', raw, ref, ref_peaks, **B)]
    for thr in (800, 1600, 3000):
        rows2.append(run(f'②+门控 deriv thr={thr}', raw, ref, ref_peaks,
                         gate_thr=thr, gate_mode='deriv', **B))
    for hold in (100, 200):
        rows2.append(run(f'②+门控 hold={hold}点 thr=800', raw, ref, ref_peaks,
                         gate_thr=800, gate_mode='hold', hold=hold, **B))
    table(rows2)

    print('\n读表提示：')
    print('  d污染 = 检测量在一拍之内被顶起的幅度，占它自身典型值的百分比，越小越好')
    print('  冻结  = 强阻断链有多少比例的时间没更新基线，太高说明它已经不工作了')
    print('  跳变  = 切换引入的最大跳变，占信号自身逐点变化的百分比')


if __name__ == '__main__':
    main()

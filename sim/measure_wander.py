# -*- coding: utf-8 -*-
"""
量实测数据里究竟有多少干扰 —— 为报告 §2.1 / §2.2 提供依据

要回答一个质疑：既然实测数据本身就有干扰，为什么还要人为注入正弦？

答案不是"实测数据干净"（恰恰相反，漂移峰峰值比注入还大），
而是注入能把能量集中在最难压的频率上，并且强度可调、可扫描。
这个脚本把两者的量级摆出来，让报告里的说法有数据支撑。
"""
import os
import sys

import numpy as np
from scipy import signal

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))   # 工程根目录 ecg_fpga/
sys.path.insert(0, os.path.join(ROOT, 'src', 'ps'))

import hw_filter_ref as hw   # noqa: E402

# 路径相对工程根目录推算，换电脑、换盘符、从任何目录启动都不用改
RAW = os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')
FS = hw.FS
LSB_MV = hw.LSB_UV / 1000.0

# 与 decide_dc_block.py 保持一致的注入值，便于对照
INJ_WANDER_MV = 2.0
INJ_WANDER_HZ = 0.2
INJ_50_UV = 224.0

WANDER_BAND = (0.05, 0.5)     # 基线漂移的常规考察频带
DC_K = 7                      # 定稿的移位位数，见 src/hls/ecg_filter_coef.h


def beat_template_corr(y, ref, pre_ms=250, post_ms=400):
    """
    按 R 波对齐后的平均心拍模板相关系数

    和 evaluate_chains.py 里的同名逻辑一致，在这里重写一份是因为
    evaluate_chains.py 末尾是裸的 main()，import 它会跑整套分析。
    """
    def tmpl(x):
        peaks = hw.find_r_peaks(x, FS)
        a, b = int(pre_ms * FS / 1000), int(post_ms * FS / 1000)
        segs = [x[p - a:p + b] for p in peaks
                if p - a >= 0 and p + b <= len(x)]
        if len(segs) < 5:
            return None
        t = np.mean(np.array(segs), axis=0)
        t = t - t.mean()
        return t / (np.linalg.norm(t) + 1e-12)

    ty, tr = tmpl(y), tmpl(ref)
    if ty is None or tr is None:
        return np.nan
    return float(np.dot(ty, tr))


def load_raw():
    with open(RAW, encoding='utf-8', errors='ignore') as f:
        vals = []
        for line in f:
            try:
                vals.append(int(line.strip()))
            except ValueError:
                pass
    return np.array(vals, dtype=np.float64)


def main():
    raw = load_raw()
    print(f'实测数据：{len(raw)} 点 = {len(raw)/FS:.1f} 秒\n')

    # ── ① 静态直流失调 ──
    print('─── ① 静态直流失调（电极极化电位）───')
    print(f'  均值 {raw.mean():.0f} 码 = {raw.mean()*LSB_MV:.3f} mV')
    print('  这是个常数，不随时间变，一阶高通就能完全去掉\n')

    # ── ② 基线漂移 ──
    # 先减掉静态失调，否则它会主导所有统计量
    x = raw - raw.mean()
    lo, hi = WANDER_BAND
    sos = signal.butter(4, [lo, hi], btype='bandpass', fs=FS, output='sos')
    wander = signal.sosfiltfilt(sos, x)      # 只为"测量"，零相移无妨

    print(f'─── ② 基线漂移（{lo}–{hi} Hz 频带）───')
    print(f"{'':>18}{'实测':>12}{'注入正弦':>12}")
    inj_rms = INJ_WANDER_MV / np.sqrt(2.0)
    print(f"{'RMS':>18}{wander.std()*LSB_MV:>11.3f}{inj_rms:>12.3f}")
    print(f"{'峰峰':>18}"
          f"{(wander.max()-wander.min())*LSB_MV:>11.3f}"
          f"{2*INJ_WANDER_MV:>12.3f}")
    print('  ★ 峰峰值上实测比注入更大 —— 实测数据的漂移并不小\n')

    print('  能量在频带内的分布（单频解调）：')
    amps = {}
    for f0 in (0.05, 0.10, 0.20, 0.30, 0.50):
        amps[f0] = hw.tone_amplitude(x, f0) * LSB_MV
        mark = '  ← 注入点' if f0 == INJ_WANDER_HZ else ''
        print(f'    {f0:>5.2f} Hz{amps[f0]:>9.3f} mV{mark}')

    peak_f = max(amps, key=amps.get)
    print(f'  → 没有哪个单频超过 {max(amps.values()):.3f} mV'
          f'（最大在 {peak_f:.2f} Hz），而频带 RMS 有 {wander.std()*LSB_MV:.3f} mV：')
    print('    说明实测漂移是**偶发的大幅摆动**（动一下、深呼吸一次），')
    print('    能量散在整个频带，不是某个频率上的稳态振荡。')
    print(f'  → 注入把 {INJ_WANDER_MV} mV 全压在 {INJ_WANDER_HZ} Hz 一个点上，')
    print(f'    在该频率上是实测的 {INJ_WANDER_MV/amps[INJ_WANDER_HZ]:.0f} 倍。')
    print('    两者测的是不同的东西：注入测**稳态衰减**（能算出 dB），')
    print('    实测的偶发摆动测**瞬态恢复**。都需要，不互相替代。\n')

    # ── ④ 直流阻断级数：实测漂移下的残留 ──
    # decide_dc_block.py 量的是"注入 2mV/0.2Hz 稳态正弦"的残留，那是稳态衰减。
    # 这里量的是实测那段**偶发摆动**过完滤波器还剩多少，
    # 并把形态代价放在同一张表里 —— 定级数要同时看这两头。
    # 2026-10-19 注：本节结论已被取代 —— 定稿不再用移位级联高通，改成
    # 矩形窗基线估计 L=320 + 延迟补偿 D=159（群延迟恒定，一个 D 对齐全部频率）。
    # 本节保留作决策过程的记录。本文件的 §① ② ③ 量的是**输入信号**有多脏，
    # 与滤波器选型无关，仍然有效。
    print(f'─── ④ 直流阻断 k={DC_K} 的级数选择（实测漂移）───')
    print('    [已取代] 定稿改用矩形窗 L=320 + D=159，本节是旧定稿的决策记录，'
          '为什么被取代见 old/README.md')
    ref_zp = hw.chain_orig_zerophase(raw)              # 形态的上限参考
    print(f"{'级数':>4}{'残留RMS':>10}{'残留峰峰':>11}"
          f"{'峰峰/QRS':>10}{'QRS':>9}{'心拍形态':>10}")
    print(f"{'':>4}{'mV':>10}{'mV':>11}{'%':>10}{'mV':>9}{'相关':>10}")
    for st in (1, 2, 3):
        d = hw.dc_block_cascade(raw, DC_K, st)         # 只过直流阻断，量残留
        w = signal.sosfiltfilt(sos, d)                 # 同一条 0.05–0.5Hz 带通
        rms = w.std() * LSB_MV
        p2p = (w.max() - w.min()) * LSB_MV
        y = hw.chain_hw(raw, k=DC_K, notch_q=15.0,      # 整条链，量形态和幅度
                        n_taps=31, stages=st)
        qrs = hw.qrs_amplitude(y, hw.find_r_peaks(y)) * LSB_MV
        tc = beat_template_corr(y, ref_zp)
        print(f'{st:>4}{rms:>10.3f}{p2p:>11.3f}'
              f'{p2p/qrs*100:>10.1f}{qrs:>9.3f}{tc:>10.4f}')
    print('  → 残留越小越好，心拍形态相关越大越好，两者反向\n')

    # ── ③ 工频 ──
    now = hw.tone_amplitude(raw, 50.0) * hw.LSB_UV
    print('─── ③ 50 Hz 工频 ───')
    print(f'  当前实测            {now:8.1f} µV   （电池供电 + 已加隔离）')
    print(f'  注入测试值          {INJ_50_UV:8.1f} µV   （修隔离之前的实测水平）')
    print(f'  → 余量 {INJ_50_UV/now:.0f} 倍，为"ADS1292→PYNQ-Z2 隔离尚未实施"预留\n')

    # ── 结论 ──
    print('─── 给报告的结论 ───')
    print('  漂移：实测已足够严苛，注入的价值在于单频定向 + 强度可扫')
    print('  工频：实测无从验证（1.9 µV），必须注入才能测出陷波器的衰减')
    print('  验收：三级比对全部用实测数据，注入数据不进测试向量')


if __name__ == '__main__':
    main()

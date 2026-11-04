# -*- coding: utf-8 -*-
"""
阶段 1 第三步：直流阻断要级联几级，陷波 Q 定多少

上一步发现单级移位直流阻断只有一阶（-20dB/十倍频），
注入 2mV/0.2Hz 呼吸漂移后还剩 0.57mV，而原来的三阶巴特沃斯只剩 0.13mV。
这里比较级联级数，并把三阶巴特沃斯作为要追平的目标。

QRS 幅度这次在**完整链路之后**测（先陷波再低通），
上一步在只过直流阻断时测的 QRS 不可信 —— 224µV 的 50Hz 会把
差分找峰算法带偏，测出来的位置和幅度都是错的。
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

# 路径相对工程根目录推算，换电脑、换盘符、从任何目录启动都不用改
RAW = os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')
FS = hw.FS
LSB_MV = hw.LSB_UV / 1000.0
INJ_50_UV = 224.0
INJ_WANDER_MV = 2.0
WANDER_HZ = 0.2


def load_raw():
    v = []
    with open(RAW, encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                v.append(int(line.strip()))
            except ValueError:
                pass
    return np.array(v, dtype=np.float64)


def quantize(c, fb):
    s = 1 << fb
    return np.round(np.asarray(c) * s) / s


def main():
    raw = load_raw()
    t = np.arange(len(raw)) / FS
    dirty = (raw
             + (INJ_50_UV / hw.LSB_UV) * np.sin(2 * np.pi * 50.0 * t)
             + (INJ_WANDER_MV / LSB_MV) * np.sin(2 * np.pi * WANDER_HZ * t))

    # 干净参考：原版零相移链路跑在干净数据上，QRS 真值从这里来
    clean_ref = hw.chain_orig_zerophase(raw)
    qrs_true = hw.qrs_amplitude(clean_ref, hw.find_r_peaks(clean_ref)) * LSB_MV
    hr_true = hw.heart_rate(hw.find_r_peaks(clean_ref))
    print(f'干净数据的 QRS 真值 {qrs_true:.3f} mV，心率 {hr_true:.1f} BPM')
    print(f'注入干扰：50Hz {INJ_50_UV:.0f} µV + {WANDER_HZ}Hz 漂移 '
          f'{INJ_WANDER_MV:.1f} mV\n')

    # 要追平的目标：原来的三阶巴特沃斯高通（单向）
    sos_hp3 = signal.butter(3, 0.5, btype='highpass', fs=FS, output='sos')
    target = signal.sosfilt(sos_hp3, dirty)
    w_t = hw.tone_amplitude(target[3*FS:-3*FS], WANDER_HZ) * LSB_MV
    print(f'【目标】三阶巴特沃斯 0.5Hz 高通（要 5 个乘法器）：'
          f'残留漂移 {w_t:.4f} mV\n')

    # ══════════════════════════════════════════════════════
    print('─── 移位直流阻断：级联几级 ───')
    print(f"{'k':>3}{'级数':>5}{'等效阶':>7}{'fc(Hz)':>9}"
          f"{'残留漂移mV':>12}{'vs目标':>9}{'乘法器':>8}")
    print('-' * 56)
    best = []
    for k in (6, 7, 8):
        for st in (1, 2, 3):
            y = hw.dc_block_cascade(dirty, k, st)
            w = hw.tone_amplitude(y[3*FS:-3*FS], WANDER_HZ) * LSB_MV
            ratio = w / w_t
            mark = '√ 达标' if w <= w_t * 1.2 else f'{ratio:.1f}倍'
            print(f'{k:>3}{st:>5}{st:>7}{hw.dc_block_fc(k):>9.3f}'
                  f'{w:>12.4f}{mark:>9}{0:>8}')
            best.append((k, st, w))
    print('  乘法器全部为 0：每级只用一个减法器 + 一个移位 + 一个累加器\n')

    # ══════════════════════════════════════════════════════
    print('─── 完整链路：直流阻断(级联) + 陷波 + FIR31，在注入干扰的数据上 ───')
    print(f"{'配置':<26}{'残留漂移':>10}{'50Hz残留':>10}"
          f"{'QRS':>8}{'QRS误差':>9}{'心率':>7}{'乘法器':>8}")
    print(f"{'':<26}{'mV':>10}{'µV':>10}{'mV':>8}{'%':>9}{'BPM':>7}{'个':>8}")
    print('-' * 78)
    h31 = hw.fir_lowpass(31, 40.0, FS)
    for k, st in ((7, 2), (7, 3), (6, 2), (8, 3)):
        for q in (15.0, 20.0, 30.0):
            b, a = hw.notch_coef(50.0, q, FS)
            b, a = quantize(b, 15), quantize(a, 15)     # Q1.15 系数
            y = hw.dc_block_cascade(dirty, k, st)
            y = hw.notch_apply(y, b, a)
            y = hw.fir_apply(y, h31)
            seg = y[3*FS:-3*FS]
            w = hw.tone_amplitude(seg, WANDER_HZ) * LSB_MV
            f50 = hw.tone_amplitude(seg, 50.0) * LSB_MV * 1000
            pk = hw.find_r_peaks(y)
            qrs = hw.qrs_amplitude(y, pk) * LSB_MV
            hr = hw.heart_rate(pk)
            err = (qrs - qrs_true) / qrs_true * 100
            print(f'{f"k={k}×{st}级  Q={q:g}":<26}{w:>10.4f}{f50:>10.2f}'
                  f'{qrs:>8.3f}{err:>9.1f}{hr:>7.1f}{5+16:>8}')
        print()

    # ══════════════════════════════════════════════════════
    print('─── Q1.15 系数量化对各 Q 值的影响（补上 Q=20）───')
    print(f"{'Q':>4}{'格式':>9}{'极点半径':>10}{'50Hz残留µV':>12}{'衰减dB':>9}")
    dc = hw.dc_block_cascade(dirty, 7, 2)
    for q in (15.0, 20.0, 30.0):
        b0, a0 = hw.notch_coef(50.0, q, FS)
        for nm, fb in (('double', None), ('Q1.15', 15)):
            b = b0 if fb is None else quantize(b0, fb)
            a = a0 if fb is None else quantize(a0, fb)
            y = hw.notch_apply(dc, b, a)
            res = hw.tone_amplitude(y[3*FS:-3*FS], 50.0) * hw.LSB_UV
            att = 20 * np.log10(max(res, 1e-9) / INJ_50_UV)
            print(f'{q:>4.0f}{nm:>9}{np.sqrt(abs(a[2])):>10.5f}'
                  f'{res:>12.3f}{att:>9.1f}')
    print()

    # ══════════════════════════════════════════════════════
    print('─── 定稿配置在干净实测数据上的表现（和原版对比）───')
    y = hw.dc_block_cascade(raw, 7, 2)
    b, a = hw.notch_coef(50.0, 20.0, FS)
    y = hw.notch_apply(y, quantize(b, 15), quantize(a, 15))
    y = hw.fir_apply(y, h31)
    pk = hw.find_r_peaks(y)
    print(f'{"":<24}{"QRS mV":>9}{"心率BPM":>9}{"心拍数":>8}{"残留直流mV":>12}')
    for nm, s in (('原版 双向零相移', clean_ref), ('定稿 硬件链', y)):
        p = hw.find_r_peaks(s)
        print(f'{nm:<24}{hw.qrs_amplitude(s,p)*LSB_MV:>9.3f}'
              f'{hw.heart_rate(p):>9.1f}{len(p):>8d}'
              f'{s[3*FS:-3*FS].mean()*LSB_MV:>12.4f}')
    print(f'\n群延迟：FIR {hw.fir_group_delay(31)} 点 = '
          f'{hw.fir_group_delay(31)/FS*1000:.0f} ms，'
          f'直流阻断和陷波再加几个点，总计约 35~40 ms')


main()

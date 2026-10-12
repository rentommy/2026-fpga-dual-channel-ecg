# -*- coding: utf-8 -*-
"""
阶段 1 第二步：50Hz 陷波器的 Q 值和定点位宽怎么选

实测数据里 50Hz 只剩 1.9 µV（RLD 修好之后），陷波器没有用武之地，
所以必须**人为注入**已知幅度的干扰来标定它。
注入幅度取 224 µV —— 这是修复前实测到的真实工频干扰水平。

要回答：
  ① Q 取多少？Q 大陷波窄、对心电影响小，但极点贴近单位圆，定点难做
  ② 系数量化到几位？Q1.15 够不够，还是要 Q2.30
  ③ 基线漂移注入后，移位直流阻断压得住吗
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
LSB_UV = hw.LSB_UV            # 1 码 = 0.048081 µV
INJECT_50_UV = 224.0          # 修复前实测的工频干扰幅度
INJECT_WANDER_MV = 2.0        # 注入的基线漂移幅度
WANDER_HZ = 0.2               # 呼吸引起的漂移典型频率


def load_raw():
    v = []
    with open(RAW, encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                v.append(int(line.strip()))
            except ValueError:
                pass
    return np.array(v, dtype=np.float64)


def quantize(c, frac_bits):
    """把系数量化到 Q(x).frac_bits 定点，返回量化后的浮点值。
    frac_bits=15 → Q1.15（16 位有符号）
    frac_bits=30 → Q2.30（32 位有符号）
    """
    s = 1 << frac_bits
    return np.round(np.asarray(c) * s) / s


def pole_radius(a):
    """二阶节 a=[1, a1, a2] 的极点半径 = sqrt(a2)。
    越接近 1，滤波器越"尖"，定点下越容易因为系数误差跑偏甚至振荡。"""
    return float(np.sqrt(abs(a[2])))


def main():
    raw = load_raw()
    n = len(raw)
    t = np.arange(n) / FS

    # ── 注入已知干扰 ──
    tone = (INJECT_50_UV / LSB_UV) * np.sin(2 * np.pi * 50.0 * t)
    wander = (INJECT_WANDER_MV * 1000 / LSB_UV) * np.sin(2 * np.pi * WANDER_HZ * t)
    dirty = raw + tone + wander

    print(f'实测数据 {n} 点 = {n/FS:.1f} 秒')
    print(f'注入 50Hz 干扰 {INJECT_50_UV:.0f} µV（修复前的真实水平）')
    print(f'注入 {WANDER_HZ} Hz 基线漂移 {INJECT_WANDER_MV:.1f} mV')
    print(f'注入后 50Hz 实测幅度 {hw.tone_amplitude(dirty, 50.0)*LSB_UV:.1f} µV\n')

    # ══════════════════════════════════════════════════════════
    #  ① 直流阻断：注入漂移后压得住吗
    # ══════════════════════════════════════════════════════════
    print('─── ① 移位直流阻断（零乘法器）───')
    print(f"{'k':>3}{'fc(Hz)':>9}{'残留0.2Hz漂移':>15}{'残留直流':>11}{'QRS幅度':>10}")
    print(f"{'':>3}{'':>9}{'mV':>15}{'mV':>11}{'mV':>10}")
    for k in (6, 7, 8, 9):
        y = hw.dc_block_shift(dirty, k)
        w = hw.tone_amplitude(y[2*FS:-2*FS], WANDER_HZ) * LSB_UV / 1000
        dc = y[2*FS:-2*FS].mean() * LSB_UV / 1000
        qrs = hw.qrs_amplitude(y, hw.find_r_peaks(y)) * LSB_UV / 1000
        print(f'{k:>3}{hw.dc_block_fc(k):>9.3f}{w:>15.4f}{dc:>11.4f}{qrs:>10.3f}')
    print('  参考：注入的漂移是 2.000 mV，原始直流失调 -3.94 mV，'
          '真实 QRS 约 1.15 mV\n')

    # ══════════════════════════════════════════════════════════
    #  ② 陷波器 Q 值
    # ══════════════════════════════════════════════════════════
    print('─── ② 50Hz 陷波器 Q 值（先用双精度系数，只看结构本身）───')
    print(f"{'Q':>4}{'带宽Hz':>8}{'极点半径':>10}{'50Hz残留':>11}{'衰减dB':>9}"
          f"{'45Hz保留':>10}{'55Hz保留':>10}")
    dc7 = hw.dc_block_shift(dirty, 7)
    for q in (10.0, 15.0, 20.0, 30.0):
        b, a = hw.notch_coef(50.0, q, FS)
        y = hw.notch_apply(dc7, b, a)
        res = hw.tone_amplitude(y[2*FS:-2*FS], 50.0) * LSB_UV
        att = 20 * np.log10(max(res, 1e-9) / INJECT_50_UV)
        # 45 / 55 Hz 处的幅频响应，看有多少心电频段被顺带削掉
        w, h = signal.freqz(b, a, worN=[45.0, 55.0], fs=FS)
        print(f'{q:>4.0f}{50.0/q:>8.2f}{pole_radius(a):>10.5f}'
              f'{res:>11.2f}{att:>9.1f}{abs(h[0]):>10.3f}{abs(h[1]):>10.3f}')
    print('  50Hz 残留单位 µV（注入 224 µV）；45/55Hz 保留 1.000 = 完全不受影响\n')

    # ══════════════════════════════════════════════════════════
    #  ③ 系数量化位宽
    # ══════════════════════════════════════════════════════════
    print('─── ③ 陷波器系数量化到定点（这一步决定 HLS 里用什么位宽）───')
    print(f"{'Q':>4}{'格式':>9}{'极点半径':>10}{'50Hz残留':>11}{'衰减dB':>9}{'稳定':>6}")
    for q in (15.0, 30.0):
        b0, a0 = hw.notch_coef(50.0, q, FS)
        for name, fb in (('double', None), ('Q1.15', 15), ('Q2.30', 30)):
            b = b0 if fb is None else quantize(b0, fb)
            a = a0 if fb is None else quantize(a0, fb)
            r = pole_radius(a)
            y = hw.notch_apply(dc7, b, a)
            res = hw.tone_amplitude(y[2*FS:-2*FS], 50.0) * LSB_UV
            att = 20 * np.log10(max(res, 1e-9) / INJECT_50_UV)
            ok = '√' if (r < 1.0 and np.all(np.isfinite(y))) else '×'
            print(f'{q:>4.0f}{name:>9}{r:>10.5f}{res:>11.2f}{att:>9.1f}{ok:>6}')
        print()

    # ══════════════════════════════════════════════════════════
    #  ④ FIR 低通抽头数
    # ══════════════════════════════════════════════════════════
    print('─── ④ FIR 低通抽头数（对称折叠后乘法器 = ceil(N/2)）───')
    print(f"{'N':>4}{'乘法器':>8}{'群延迟ms':>10}{'50Hz衰减dB':>12}"
          f"{'100Hz衰减dB':>13}{'QRS幅度mV':>11}")
    b15, a15 = hw.notch_coef(50.0, 15.0, FS)
    notched = hw.notch_apply(dc7, b15, a15)
    for nt in (15, 23, 31, 47, 63):
        h = hw.fir_lowpass(nt, 40.0, FS)
        w, hh = signal.freqz(h, [1.0], worN=[50.0, 100.0], fs=FS)
        y = hw.fir_apply(notched, h)
        qrs = hw.qrs_amplitude(y, hw.find_r_peaks(y)) * LSB_UV / 1000
        print(f'{nt:>4}{int(np.ceil(nt/2)):>8}{hw.fir_group_delay(nt)/FS*1000:>10.0f}'
              f'{20*np.log10(abs(hh[0])):>12.1f}'
              f'{20*np.log10(abs(hh[1])):>13.1f}{qrs:>11.3f}')
    print('  真实 QRS 约 1.15 mV，掉太多说明低通把 QRS 的高频成分削掉了\n')

    # ══════════════════════════════════════════════════════════
    #  ⑤ 数据通路位宽
    # ══════════════════════════════════════════════════════════
    print('─── ⑤ 数据通路需要多宽 ───')
    y1 = hw.dc_block_shift(dirty, 7)
    y2 = hw.notch_apply(y1, b15, a15)
    y3 = hw.fir_apply(y2, hw.fir_lowpass(31, 40.0, FS))
    for nm, s in (('输入（ADS1292 24位）', dirty), ('① 直流阻断后', y1),
                  ('② 陷波后', y2), ('③ FIR 后', y3)):
        mx = np.abs(s).max()
        bits = int(np.ceil(np.log2(mx + 1))) + 1      # +1 给符号位
        print(f'{nm:<22} 峰值 {mx:>10.0f} 码  → 至少 {bits:>2d} 位有符号')
    print('  注：FIR 内部累加器还要再宽 log2(抽头数) ≈ 5 位，防止中间溢出')


main()

# -*- coding: utf-8 -*-
"""
阶段 1 收尾：生成 HLS 要用的系数头文件和测试向量

定稿配置（依据见 report/design_phase1.md）：
  ① 直流阻断  移位式，k=7（fc=0.622Hz），级联 2 级   → 0 个乘法器
  ② 50Hz 陷波 二阶 biquad，Q=15，系数 Q2.16（18位）  → 5 个乘法器
  ③ 低通      31 抽头对称 FIR，40Hz，系数 Q1.19（18位）→ 16 个乘法器（折叠后）
  合计每通道 21 个乘法器

系数为什么是 18 位：
  DSP48E1（7 系列的乘法单元）是 25×18 有符号乘法器，18 位正好是系数端口的
  原生宽度 —— 用 18 位不比用 16 位多花任何资源，精度却高 4 倍。
  陷波器的 b1/a1 = -2cos(2π·50/500) = ±1.618，整数位必须留 2 位，所以是 Q2.16。
  FIR 系数最大只有 0.159，纯小数，可以给到 19 位小数。

产出：
  src/hls/ecg_filter_coef.h   系数 + 参数，HLS 直接 include
  data/input_raw.txt          输入：实测 ADC 码
  data/golden_float.txt       期望输出：浮点参考链的结果
  data/testcase_impulse.txt   单位冲激，用来验证 FIR 系数有没有搞反
  data/testcase_50hz.txt      纯 50Hz 正弦，用来验证陷波器
"""
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'ps'))

import hw_filter_ref as hw   # noqa: E402

# 路径相对工程根目录推算，换电脑、换盘符、从任何目录启动都不用改
RAW = os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')
FS = hw.FS

# ── 定稿参数 ──
DC_K = 7            # 移位位数，fc = 500/(2π·128) = 0.622 Hz
DC_STAGES = 2       # 级联级数
NOTCH_F0 = 50.0
NOTCH_Q = 15.0      # 极点半径最小(0.979)，对系数量化最不敏感
FIR_TAPS = 31
FIR_FC = 40.0

COEF_BITS = 18      # 系数存储位宽 = DSP48E1 乘法器系数端口的原生宽度
NOTCH_FRAC = 16     # Q2.16：b1/a1 = ±1.618，整数位要留 2 位
FIR_FRAC = 19       # Q1.19：FIR 系数最大 0.159，纯小数，小数位可以给更多


def to_fixed(x, frac, bits=COEF_BITS, tag=''):
    """浮点 → 定点整数，并检查装不装得下"""
    v = np.round(np.asarray(x) * (1 << frac)).astype(np.int64)
    lim = (1 << (bits - 1)) - 1
    assert np.all(np.abs(v) <= lim), \
        f'{tag}系数超出 {bits} 位范围（上限 {lim}）: {list(v)}'
    return v


def main():
    # ── 读实测数据 ──
    vals = []
    with open(RAW, encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                vals.append(int(line.strip()))
            except ValueError:
                pass
    raw = np.array(vals, dtype=np.int64)
    print(f'实测数据 {len(raw)} 点 = {len(raw)/FS:.1f} 秒')

    # ── 系数 ──
    b_n, a_n = hw.notch_coef(NOTCH_F0, NOTCH_Q, FS)
    h = hw.fir_lowpass(FIR_TAPS, FIR_FC, FS)

    # biquad 的 a0 恒为 1，不用存；HLS 里只需要 b0 b1 b2 a1 a2
    b_q = to_fixed(b_n, NOTCH_FRAC, tag='陷波 b ')
    a_q = to_fixed(a_n, NOTCH_FRAC, tag='陷波 a ')
    h_q = to_fixed(h, FIR_FRAC, tag='FIR ')
    assert a_q[0] == (1 << NOTCH_FRAC), 'a0 应该正好是 1.0'

    print(f'\n陷波器 Q={NOTCH_Q:g}  极点半径 {np.sqrt(abs(a_n[2])):.5f}')
    print(f'  浮点 b = {b_n}')
    print(f'  浮点 a = {a_n}')
    print(f'  Q2.{NOTCH_FRAC}: b = {list(b_q)}   a1 = {a_q[1]}  a2 = {a_q[2]}')
    print(f'\nFIR {FIR_TAPS} 抽头，Q1.{FIR_FRAC}')
    print(f'  对称性检查：最大不对称量 {np.abs(h_q - h_q[::-1]).max()}（必须为 0，'
          f'否则不能折叠）')
    print(f'  系数和 / 2^{FIR_FRAC} = {h_q.sum()/(1<<FIR_FRAC):.6f}'
          f'（直流增益，应接近 1.0）')

    # ── 写头文件 ──
    hls_dir = os.path.join(ROOT, 'src', 'hls')
    hdr = os.path.join(hls_dir, 'ecg_filter_coef.h')
    with open(hdr, 'w', encoding='utf-8', newline='\n') as f:
        acc_bits = 24 + COEF_BITS + int(np.ceil(np.log2(FIR_TAPS)))
        f.write(f'''// ecg_filter_coef.h  —— 由 sim/gen_vectors.py 自动生成，不要手改
//
// 心电预处理滤波链的定点系数，采样率 {FS} Hz
//
// 链路：直流阻断(移位 k={DC_K} × {DC_STAGES} 级) → 50Hz 陷波(Q={NOTCH_Q:g}) → {FIR_TAPS} 抽头 FIR 低通({FIR_FC:g}Hz)
//
// 每通道每采样点的乘法**次数**：0 + 5 + {int(np.ceil(FIR_TAPS/2))} = {5 + int(np.ceil(FIR_TAPS/2))}
// 注意这是次数不是乘法器个数：500 SPS 下每个采样周期有 200,000 个 100MHz 时钟，
// 8 通道共 {(5 + int(np.ceil(FIR_TAPS/2)))*8} 次乘法，一个 DSP48 时分复用即可（占用率 0.08%）。
// 架构依据见 report/design_phase1.md 第 2.0 节。
//
// 系数一律 {COEF_BITS} 位有符号 —— DSP48E1 是 25x18 乘法器，18 位是系数端口的
// 原生宽度，比 16 位精度高 4 倍而不多占资源。

#ifndef ECG_FILTER_COEF_H
#define ECG_FILTER_COEF_H

#define ECG_FS          {FS}
#define COEF_BITS       {COEF_BITS}

// ── ① 直流阻断（零乘法器）──
//   for (s = 0; s < DC_STAGES; s++) {{
//       acc[s] += (x - acc[s]) >> DC_SHIFT;
//       x       = x - acc[s];
//   }}
// 单级是一阶高通，fc = FS / (2*pi*2^DC_SHIFT) = {hw.dc_block_fc(DC_K):.3f} Hz
// 级联 {DC_STAGES} 级得到 {DC_STAGES} 阶，注入 2mV/0.2Hz 呼吸漂移实测残留 0.17mV
#define DC_SHIFT        {DC_K}
#define DC_STAGES       {DC_STAGES}

// ── ② 50Hz 陷波 biquad，直接 I 型，系数 Q2.{NOTCH_FRAC} ──
//   acc  = B0*x[n] + B1*x[n-1] + B2*x[n-2] - A1*y[n-1] - A2*y[n-2];
//   y[n] = acc >> NOTCH_FRAC;
// 极点半径 {np.sqrt(abs(a_n[2])):.5f}。注入 224uV 工频实测衰减 -61.9 dB
#define NOTCH_FRAC      {NOTCH_FRAC}
#define NOTCH_ONE       {1 << NOTCH_FRAC}
#define NOTCH_B0        {b_q[0]}
#define NOTCH_B1        {b_q[1]}
#define NOTCH_B2        {b_q[2]}
#define NOTCH_A1        {a_q[1]}
#define NOTCH_A2        {a_q[2]}

// ── ③ FIR 低通，系数对称，可折叠成 {int(np.ceil(FIR_TAPS/2))} 个乘法器，系数 Q1.{FIR_FRAC} ──
//   折叠写法：h[i] * (x[n-i] + x[n-(FIR_TAPS-1-i)])，一个乘法算两项
#define FIR_TAPS        {FIR_TAPS}
#define FIR_FRAC        {FIR_FRAC}
#define FIR_ONE         {1 << FIR_FRAC}
#define FIR_DELAY       {hw.fir_group_delay(FIR_TAPS)}      // 群延迟 = {hw.fir_group_delay(FIR_TAPS)/FS*1000:.0f} ms，算 RR 间期时被减掉

static const int FIR_COEF[FIR_TAPS] = {{
''')
        for i in range(0, FIR_TAPS, 8):
            chunk = ', '.join(f'{int(v):7d}' for v in h_q[i:i + 8])
            f.write(f'    {chunk},\n' if i + 8 < FIR_TAPS else f'    {chunk}\n')
        f.write(f'''}};

// ── 数据通路位宽（依据 sim/characterize_notch.py 第 5 节实测峰值）──
//   输入      24 位有符号（ADS1292 原生输出）
//   各级中间  24 位有符号足够，实测各级峰值不到 19 位
//   FIR 累加器 24 + {COEF_BITS} + ceil(log2({FIR_TAPS})) = {acc_bits} 位 → 取 48 位（DSP48 原生累加宽度）
#define DATA_BITS       24
#define ACC_BITS        48

#endif // ECG_FILTER_COEF_H
''')
    print(f'\n已写 {os.path.relpath(hdr, ROOT)}')

    # ── 参考输出 ──
    def chain(x):
        """黄金参考：结构和位宽与 HLS 一致，但算术用双精度。
        HLS 的定点版本与这条链的差异，就是"算术量化误差"，
        C 仿真时要报出来并设阈值。"""
        y = hw.dc_block_cascade(x, DC_K, DC_STAGES)
        y = hw.notch_apply(y, b_q / (1 << NOTCH_FRAC), a_q / (1 << NOTCH_FRAC))
        return hw.fir_apply(y, h_q / (1 << FIR_FRAC))

    data_dir = os.path.join(ROOT, 'data')

    def dump(name, arr, fmt):
        p = os.path.join(data_dir, name)
        with open(p, 'w', encoding='ascii', newline='\n') as f:
            f.writelines(fmt % v + '\n' for v in arr)
        print(f'  {name:<26} {len(arr):>6} 行')

    print('\n测试向量：')
    dump('input_raw.txt', raw, '%d')
    dump('golden_float.txt', chain(raw.astype(np.float64)), '%.6f')

    # 单位冲激：输出应该正好是各级响应的卷积，用来抓"系数装反/装错"
    imp = np.zeros(256, dtype=np.float64)
    imp[8] = 1 << 20                      # 放大一点，免得定点下被截断成 0
    dump('testcase_impulse.txt', imp.astype(np.int64), '%d')
    dump('testcase_impulse_golden.txt', chain(imp), '%.6f')

    # 纯 50Hz：输出应该被压到接近 0，用来抓陷波器没生效
    t = np.arange(2000) / FS
    s50 = (1 << 18) * np.sin(2 * np.pi * 50.0 * t)
    dump('testcase_50hz.txt', np.round(s50).astype(np.int64), '%d')
    dump('testcase_50hz_golden.txt', chain(np.round(s50)), '%.6f')

    # ── 最后校验 ──
    y = chain(raw.astype(np.float64))
    ref = hw.chain_orig_zerophase(raw.astype(np.float64))
    pk_y, pk_r = hw.find_r_peaks(y), hw.find_r_peaks(ref)
    LSB_MV = hw.LSB_UV / 1000.0
    print('\n定稿链路 vs 原版双向零相移（干净实测数据）：')
    print(f'{"":<22}{"QRS mV":>9}{"心率BPM":>10}{"心拍数":>8}')
    print(f'{"原版 双向零相移":<22}{hw.qrs_amplitude(ref,pk_r)*LSB_MV:>9.3f}'
          f'{hw.heart_rate(pk_r):>10.1f}{len(pk_r):>8d}')
    print(f'{"定稿 硬件链":<22}{hw.qrs_amplitude(y,pk_y)*LSB_MV:>9.3f}'
          f'{hw.heart_rate(pk_y):>10.1f}{len(pk_y):>8d}')
    print(f'\n50Hz 纯音测试：输入幅度 {1<<18} 码，'
          f'输出残留 {hw.tone_amplitude(chain(np.round(s50))[500:], 50.0):.2f} 码')


main()

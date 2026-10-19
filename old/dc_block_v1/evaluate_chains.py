# -*- coding: utf-8 -*-
"""
阶段 1 第一步：用真实实测数据比较候选滤波链，把结构参数定下来

要回答三个问题：
  ① 双向零相移改成单向因果，差多少？
  ② 换成硬件友好结构（移位直流阻断 + biquad 陷波 + 对称 FIR），还差多少？
  ③ 哪一组参数（k / Q / FIR 抽头数）在"效果"和"乘法器个数"之间最划算？

输出一张表 + 模型推理一致性检查。表里的数字直接进设计报告。
"""
import os
import sys
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')                      #设置输出编码
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))             #工程根目录 ecg_fpga/
sys.path.insert(0, os.path.join(ROOT, 'src', 'ps'))           #添加hw_filter_ref库路径

import hw_filter_ref as hw   # 滤波器参考函数


# 路径全部相对工程根目录推算，换电脑、换盘符、从任何目录启动都不用改
RAW = os.path.join(ROOT, 'data', 'source', 'ecg_60s_500sps.txt')
MODEL = os.path.join(ROOT, 'model', 'ecg_model.onnx')
CLASSES = os.path.join(ROOT, 'model', 'ecg_model_classes.txt')

FS = hw.FS
LSB_MV = hw.LSB_UV / 1000.0      # 1 码 = 4.8081e-5 mV



def load_raw(path):
    """
    加载数据
    """
    vals = []
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                vals.append(int(line.strip()))
            except ValueError:
                pass
    return np.array(vals, dtype=np.float64)


def align_and_corr(y, ref):
    """
    群延迟
    全局对齐后的相关系数
    """
    n = min(len(y), len(ref))
    m = 2 * FS                  # 掐掉两端各 2 秒，避开滤波器启动瞬态
    a = y[m:n - m] - y[m:n - m].mean()
    b = ref[m:n - m] - ref[m:n - m].mean()
    best_lag, best_r = 0, -2.0
    for lag in range(0, 101):   # 0~200ms，群延迟不会超过这个量级
        aa = a[lag:]
        bb = b[:len(aa)]
        r = float(np.dot(aa, bb) / (np.linalg.norm(aa) * np.linalg.norm(bb)))
        if r > best_r:
            best_r, best_lag = r, lag
    return best_lag, best_r


def beat_template(x, fs=FS, pre_ms=250, post_ms=400):
    """
    心跳波形平均叠加
    L2 归一化
    """
    peaks = hw.find_r_peaks(x, fs)
    a = int(pre_ms * fs / 1000)
    b = int(post_ms * fs / 1000)
    segs = [x[p - a:p + b] for p in peaks
            if p - a >= 0 and p + b <= len(x)]
    if len(segs) < 5:
        return None
    t = np.mean(np.array(segs), axis=0)
    t = t - t.mean()
    return t / (np.linalg.norm(t) + 1e-12)


def template_corr(y, ref):
    """
    心跳波形相关系数
    """
    ty, tr = beat_template(y), beat_template(ref)
    if ty is None or tr is None:
        return np.nan
    return float(np.dot(ty, tr))


def n_multipliers(n_taps, use_notch=True):
    """估算每通道每采样点的乘法次数。
    · 移位直流阻断：0
    · biquad 陷波：5（b0 b1 b2 a1 a2）
    · 对称 FIR：ceil(n_taps/2)
    """
    return (5 if use_notch else 0) + int(np.ceil(n_taps / 2))


def evaluate(name, y, ref, n_mult, extra=''):
    """
    评估参数计算
    """
    dc = y[2 * FS:-2 * FS].mean() * LSB_MV                              #残留直流
    f50 = hw.tone_amplitude(y[2 * FS:-2 * FS], 50.0) * LSB_MV * 1000    #残留50Hz
    peaks = hw.find_r_peaks(y)                                          #R波数
    qrs = hw.qrs_amplitude(y, peaks) * LSB_MV                           #QRS幅度
    bpm = hw.heart_rate(peaks)                                          #心率
    lag, r = align_and_corr(y, ref) if ref is not None else (0, 1.0)    #lag:群延迟, r:全局对齐后的相关系数
    tc = template_corr(y, ref) if ref is not None else 1.0              #template_corr
    return dict(name=name, dc=dc, f50=f50, qrs=qrs, bpm=bpm,
                n_beat=len(peaks), lag=lag, r=r, tc=tc,
                n_mult=n_mult, extra=extra)
















def main():
    raw = load_raw(RAW)                                                              #加载数据 原始数据
    print(f'实测数据：{len(raw)} 点 = {len(raw)/FS:.1f} 秒')                          #原始数据信息
    print(f'原始码范围 [{raw.min():.0f}, {raw.max():.0f}]，'
          f'均值 {raw.mean():.0f}（= 直流失调 {raw.mean()*LSB_MV:.2f} mV）')
    print(f'原始 50Hz 幅度 {hw.tone_amplitude(raw, 50.0)*LSB_MV*1000:.1f} µV\n')






#计算滤波指标，比较滤波参数
    # ── 移位位数对应的截止频率 ──
    print('直流阻断的移位位数 k 与截止频率：')
    for k in (6, 7, 8, 9):
        print(f'  k={k}  →  fc = {hw.dc_block_fc(k):.3f} Hz'           #对比不同K和截止频率的关系
              f'{"   ← 最接近原来的 0.5Hz" if k == 7 else ""}')
    print()

    # ── 参考：双向零相移（硬件做不到，只作上限）──
    ref = hw.chain_orig_zerophase(raw)                        #巴特沃斯带通 + 陷波

    rows = [evaluate('① 原版 双向零相移 sosfiltfilt', ref, None, np.nan,'硬件做不到，仅作上限参考')]                        #双向 巴特沃斯带通 + 陷波(对比参考的指标)
    rows.append(evaluate('② 原版结构 改单向 sosfilt',hw.chain_orig_causal(raw), ref, np.nan,'只去掉反向滤，结构不变'))      #单向 巴特沃斯带通 + 陷波(对比参考的指标)

    # ── 硬件候选 ──
    cands = [
        dict(k=7, q=30.0, n=31),               #参数组合列表
        dict(k=8, q=30.0, n=31),
        dict(k=7, q=15.0, n=31),
        dict(k=8, q=15.0, n=31),
        dict(k=8, q=30.0, n=15),
        dict(k=8, q=30.0, n=63),
        dict(k=7, q=15.0, n=31, s=2),          #定稿组合：直流阻断 2 级
    ]
    for c in cands:
        s = c.get('s', 1)                                                 #未写 s 的按单级算，保持原有六行结果不变
        y = hw.chain_hw(raw, k=c['k'], notch_q=c['q'], n_taps=c['n'], stages=s)     #候选组合测试通过完整硬件滤波链路滤波后，指标计算
        rows.append(evaluate(
            f"③ 硬件链 k={c['k']} Q={c['q']:g} FIR={c['n']}"
            f"{'' if s == 1 else f' ×{s}级 ←定稿'}",
            y, ref, n_multipliers(c['n']),
            f"FIR群延迟 {hw.fir_group_delay(c['n'])} 点 "
            f"= {hw.fir_group_delay(c['n'])/FS*1000:.0f} ms"))

    # ── 打表 ──
    print('=' * 124)
    print(f"{'链路':<34}{'残留直流':>10}{'QRS':>8}{'心率':>7}{'心拍':>5}"      #终端表头
          f"{'延迟':>7}{'心拍形态':>10}{'全局r':>8}{'乘法':>6}")
    print(f"{'':<34}{'mV':>10}{'mV':>8}{'BPM':>7}{'个':>5}"                   #表头单位
          f"{'ms':>7}{'相关':>10}{'(失效)':>8}{'个':>6}")
    print('-' * 124)
    for d in rows:                                                            #展示指标
        nm = '--' if np.isnan(d['n_mult']) else f"{d['n_mult']:.0f}"
        print(f"{d['name']:<34}{d['dc']:>10.3f}"
              f"{d['qrs']:>8.3f}{d['bpm']:>7.1f}{d['n_beat']:>5d}"
              f"{d['lag']/FS*1000:>7.0f}{d['tc']:>10.4f}{d['r']:>8.3f}{nm:>6}")
    print('=' * 124)
    for d in rows:
        if d['extra']:
            print(f"  {d['name']}：{d['extra']}")                              #打印每种滤波方案的备注信息
    print()





    # ── 模型推理一致性 ──
    check_inference(raw, ref)                   #输入原始数据、双向零相移参考数据，比较模型对滤波效果的分类








def check_inference(raw, ref):
    """
    同一段数据，分别用零相移参考链和硬件链预处理，看模型判读是否一致。
    这是端到端的验收：滤波结构改了，最终结论不能变。
    """

    try:                                                              #检查是否安装onnxruntime库
        import onnxruntime as ort
    except ImportError:
        print('（没装 onnxruntime，跳过推理一致性检查）')
        return
    from scipy import signal as sg


#读取模型基本信息
    sess = ort.InferenceSession(MODEL, providers=['CPUExecutionProvider'])       #读取深度学习模型文件，设置计算方式
    inp = sess.get_inputs()[0].name                                              #读取模型数据输入口的名称（不同的输入数据对应不同的输入口，模型只有一种输入固定使用第[0]个）
    classes = [l.strip() for l in open(CLASSES, encoding='utf-8') if l.strip()]  #读取分类结果类型表


    def infer(x_500):
        """
        输入波形数据
        预处理
        模型计算
        输出分类结果和概率
        """
        x = sg.resample_poly(x_500, 18, 25)          # 500 → 360 Hz 重采样
        if len(x) != 3600:                           #统一数据长度
            x = np.resize(x, 3600)
        x = (x - x.mean()) / (x.std() + 1e-8)        #归一化
        lo = sess.run(None, {inp: x.reshape(1, 1, 3600).astype(np.float32)})[0][0]   #模型计算
        e = np.exp(lo - lo.max())
        p = e / e.sum()                           #计算分类概率
        k = int(np.argmax(p))
        return classes[k], float(p[k])            #输出分类结果


    # 定稿参数，与 src/hls/ecg_filter_coef.h 一致（DC_SHIFT / DC_STAGES / Q / FIR_TAPS）
    FIN_K, FIN_STAGES, FIN_Q, FIN_N = 7, 2, 15.0, 31
    hw_y = hw.chain_hw(raw, k=FIN_K, notch_q=FIN_Q,
                       n_taps=FIN_N, stages=FIN_STAGES)                   #完整硬件滤波链路滤波

    lbl = f'硬件链 k={FIN_K}×{FIN_STAGES}级 Q={FIN_Q:g} FIR={FIN_N}'      #标签由参数算出，不会和实际跑的配置脱节

    print('模型推理一致性（10 秒不重叠窗口，跳过前 2 秒瞬态）：')
    print(f"{'窗口':<6}{'零相移参考':>20}{lbl:>28}{'一致':>6}")  #打表
    print('-' * 62)

    same = 0
    total = 0
    start = 2 * FS
    while start + 10 * FS <= len(raw):                                    #10秒循环窗口
        a = infer(ref[start:start + 10 * FS])                             #截取原始数据
        b = infer(hw_y[start:start + 10 * FS])                            #截取参考数据
        ok = a[0] == b[0]                                                 #比较模型分类结果
        same += ok                                                        #统计分类结果一致的窗口数
        total += 1                                                        #统计总窗口数
        print(f'{total:<6}{a[0]+" "+f"{a[1]*100:.1f}%":>20}'              #输出全部分类比较结果
              f'{b[0]+" "+f"{b[1]*100:.1f}%":>28}{"√" if ok else "×":>6}')
        start += 10 * FS                                                  #移动窗口
    print('-' * 62)
    print(f'一致 {same}/{total}')                                         #完全一致的窗口数比例





main()      #执行主函数

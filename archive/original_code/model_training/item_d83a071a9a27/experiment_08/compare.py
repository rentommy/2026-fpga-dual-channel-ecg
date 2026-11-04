import json
import numpy as np
from run import ROOT,save,sha

def verify():
    old=ROOT.parent/'experiment_07/data'
    with np.load(old/'beats.npz') as a, np.load(ROOT/'data/beats.npz') as b:
        for key in ['y','r','db','group','split']:
            assert np.array_equal(a[key],b[key]),key
        ax=a['x'];bx=b['x']
        assert np.array_equal(ax[:,1],bx[:,1])
        assert np.isfinite(bx).all() and np.all(bx[:,0][bx[:,1]==0]==0)
        assert np.any(ax[:,0]!=bx[:,0]),'No waveform change'
        difference=float(np.sqrt(np.mean((ax[:,0]-bx[:,0])**2)))
    assert (old/'beats.csv').read_bytes()==(ROOT/'data/beats.csv').read_bytes()
    assert (old/'split.json').read_bytes()==(ROOT/'data/split.json').read_bytes()
    save(ROOT/'controlled_comparison_audit.json',{'passed':True,'same_labels_rr_groups_split_masks_and_positions':True,
        'waveform_rms_difference_mV_including_padding':difference,'old_sha256':sha(old/'beats.npz'),'new_sha256':sha(ROOT/'data/beats.npz')})

def report():
    rows=[]
    for variant,folder in [('原双向带通',ROOT.parent/'experiment_07'),('双向带通＋50Hz陷波',ROOT)]:
        values=[json.loads((folder/'runs'/f'multi_z_mixed_seed{s}'/'val_metrics.json').read_text()) for s in range(3)]
        rows.append({'variant':variant,'accuracy_mean':float(np.mean([v['accuracy'] for v in values])),
                     'accuracy_sd':float(np.std([v['accuracy'] for v in values])),
                     'macro_f1_mean':float(np.mean([v['macro_f1'] for v in values])),
                     'macro_f1_sd':float(np.std([v['macro_f1'] for v in values])),'seeds':values})
    save(ROOT/'comparison.json',rows)
    lines=['# 双向带通＋50Hz陷波对照结果','','滤波完全按用户图片参数：三阶0.5–40Hz带通双向滤波，再做50Hz、Q=30陷波双向滤波，之后重采样到256Hz。',
           '原方案已经是双向带通，本轮唯一新增处理为50Hz陷波。保留原始数据与旧实验，不覆盖。', '',
           '同一多尺度残差＋RR结构、逐拍标准化、MIT＋INCART训练患者、三个相同种子、训练配置与MIT验证集。审计确认标签、RR、患者划分、中心位置、有效掩码完全一致，只有波形数值改变。', '',
           '| 方案 | 准确率均值±种子标准差 | macro-F1均值±种子标准差 |','|---|---:|---:|']
    for r in rows:lines.append(f"| {r['variant']} | {r['accuracy_mean']:.2%} ± {r['accuracy_sd']:.2%} | {r['macro_f1_mean']:.4f} ± {r['macro_f1_sd']:.4f} |")
    da=rows[1]['accuracy_mean']-rows[0]['accuracy_mean'];df=rows[1]['macro_f1_mean']-rows[0]['macro_f1_mean']
    lines+=['',f'本轮观察到的平均准确率变化为{da*100:+.2f}个百分点，macro-F1变化为{df:+.4f}。三组macro-F1均未超过原方案，当前没有整体改善证据，七类80%目标仍未达到。V类及伪迹部分指标改善，A/F/L/R召回下降。不能仅凭三种子把变化归因于陷波必然有害，也不能把局部类别改善说成整体达标。']
    lines+=['','| 种子 | 原准确率 | 陷波准确率 | 原macro-F1 | 陷波macro-F1 |','|---|---:|---:|---:|---:|']
    for s in range(3):
        a,b=rows[0]['seeds'][s],rows[1]['seeds'][s]
        lines.append(f"| {s} | {a['accuracy']:.2%} | {b['accuracy']:.2%} | {a['macro_f1']:.4f} | {b['macro_f1']:.4f} |")
    lines+=['','| 类别 | 原精确率 | 陷波精确率 | 原召回率 | 陷波召回率 |','|---|---:|---:|---:|---:|']
    for c in ['A','F','L','N','R','V','|']:
        vals=[np.mean([v['report'][c][k] for v in r['seeds']]) for k in ['precision','recall'] for r in rows]
        label=c.replace('|','\\|');lines.append('| '+label+' | '+' | '.join(f'{v:.2%}' for v in vals)+' |')
    lines+=['','本轮只进行开发验证对照，没有再次使用已查看过的外部测试挑选滤波参数。三种子标准差不是患者总体置信区间；三次训练不能独立证明统计显著性。',
            '双向滤波依赖未来信号，仍为离线方案。没有把MIT-BIH的工频默认认定为50Hz；这里按用户指定参数实验。新增陷波不保证识别提升，也不补充缺失的患者类别。',
            '训练权重、配置、预测、每轮历史均已保存；未自动替换部署权重。']
    (ROOT/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    import sys
    verify() if sys.argv[1]=='verify' else report()

"""Explain completed comparisons; never modifies selection or weights."""
import json,csv
import numpy as np
from study import ROOT,CLASSES,table
def result(name,seed=0):return json.loads((ROOT/'runs'/f'{name}_seed{seed}/val_metrics.json').read_text())
selected=json.loads((ROOT/'selection.json').read_text())['selected']
baseline=[result('baseline',s) for s in [0,1,2]];winner=[result(selected,s) for s in [0,1,2]]
b=np.array([r['macro_f1'] for r in baseline]);w=np.array([r['macro_f1'] for r in winner]);delta=w-b
lines=['# 五项工作完成情况与结论','',f'按预定 seed0 规则选出的方案为 **{selected}**。三种子开发验证 macro-F1：基线 {b.mean():.4f} ± {b.std():.4f}，所选方案 {w.mean():.4f} ± {w.std():.4f}。同编号种子差值为 {delta.round(4).tolist()}。',
       '这里的 ± 是三个训练种子的标准差，不是置信区间；方案曾在同一验证集筛选，结果仍可能乐观。',
       '', '| 类别 | 基线精确率均值 | 所选精确率均值 | 基线召回均值 | 所选召回均值 |','|---|---:|---:|---:|---:|']
for c in CLASSES:
    label=c.replace('|','\\|');bp=np.mean([r['report'][c]['precision'] for r in baseline]);wp=np.mean([r['report'][c]['precision'] for r in winner]);br=np.mean([r['report'][c]['recall'] for r in baseline]);wr=np.mean([r['report'][c]['recall'] for r in winner])
    lines.append(f'| {label} | {bp:.2%} | {wp:.2%} | {br:.2%} | {wr:.2%} |')
lines+=['','## 五项逐一落实','',
    '1. **错误审核完成。** 原始标注、重建预处理与实际网络输入一致；保存九张逐记录对照图。A 验证样本集中在 232，R 在 124 与 232 的识别表现悬殊。未因此删除困难记录。详见 waveform_review/审核说明.md。',
    '2. **采样对照完成。** 额外设置普通损失 uniform 对照，将采样作用与损失权重变化分开。','']
for a,z,title in [('baseline','uniform','去掉损失权重'),('uniform','balanced','在普通损失下改变采样'),('baseline','morph_only','去掉 RR 信息'),('baseline','rr_only','仅使用 RR 小网络'),('baseline','feature_fusion','加入局部形态特征'),('balanced','balanced_shift','轻微位置平移'),('balanced','balanced_scale','轻微幅值缩放'),('balanced','balanced_noise','轻噪声'),('balanced','balanced_all','三项增强组合')]:
    aa=result(a);zz=result(z)
    lines.append(f'- {title}：seed0 macro-F1 {aa["macro_f1"]:.4f} → {zz["macro_f1"]:.4f}；A 召回率 {aa["report"]["A"]["recall"]:.2%} → {zz["report"]["A"]["recall"]:.2%}。')
lines+=['','3. **形态/RR 对照完成。** 比较仅形态、仅 RR、二者联合，以及显式局部形态描述融合。显式描述量是原时间轴局部能量、幅值、斜率等，未冒称实现临床 QRS 起止检测。',
    '4. **三种增强及组合完成。** 所有增强只用于训练，分别与相同采样、不增强版本比较。训练标签、验证样本保持一致。',
    '5. **多种子与逐受试者评估完成。** 十个 seed0 方案及基线/所选方案的额外两个种子，保存逐受试者精确率与召回率；未使用旧测试选择方案，也未挑单个最好种子。',
    '', '## 结论边界','',
    '改进是否值得采用，应同时看上表精确率、召回率和多种子结果；总体分数增加不等于所有类别改善。L/R 来源不足，不能用增强或重复抽拍代替补充新受试者。',
    '当前基线按本轮代码重新训练，单种子成绩可能与上一轮有小幅差异；实际对照采用本轮同设置的基线与方案，不将跨轮差值当成单因素收益。',
    '尚未完成新的独立外部测试、自动心拍检测或硬件部署验证。本轮不会替换部署权重。']
if w.mean()<=b.mean():lines+=['','**多种子均值未超过基线，不能认为所选方案已带来可靠提升。**']
else:lines+=['',f'**所选方案的三种子平均 macro-F1 比基线增加 {w.mean()-b.mean():.4f}；这是当前开发验证上的增益，仍需独立验证。**']
if np.any(delta<0):lines+=['','**重复实验未显示一致收益，不能确认稳定提升。所选方案不自动替换基线。**']
patient={}
for name in dict.fromkeys(['baseline',selected]):
    patient[name]={}
    for seed in [0,1,2]:
        with (ROOT/'runs'/f'{name}_seed{seed}/per_patient.csv').open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if not int(row['support']):continue
                key=(row['group'],row['class']);patient[name].setdefault(key,[]).append(float(row['recall']))
comparison=[]
for key,values in patient['baseline'].items():
    other=patient[selected][key]
    comparison.append({'group':key[0],'class':key[1],'baseline_recall_seed_mean':float(np.mean(values)),'selected_recall_seed_mean':float(np.mean(other)),'difference':float(np.mean(other)-np.mean(values))})
table(ROOT/'per_patient_comparison.csv',comparison)
lines+=['','## 将每位受试者等权看待','', '| 类别 | 有样本来源组数 | 基线各组召回均值 | 所选各组召回均值 |','|---|---:|---:|---:|']
for c in CLASSES:
    subset=[r for r in comparison if r['class']==c];label=c.replace('|','\\|')
    lines.append(f'| {label} | {len(subset)} | {np.mean([r["baseline_recall_seed_mean"] for r in subset]):.2%} | {np.mean([r["selected_recall_seed_mean"] for r in subset]):.2%} |')
lines+=['','此表先在每个来源内对三个种子取均值，再对来源等权平均，与前表按心拍汇总的召回率口径不同。L 只有一个验证来源，不能据此证明广泛泛化。逐来源差值见 per_patient_comparison.csv。']
(ROOT/'五项工作总结.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Five-item evidence summary saved.')

"""Generate a readable report from completed run artifacts, including grouped A audit."""
import argparse,csv,json
from pathlib import Path
import numpy as np
from pipeline import ROOT,CLASSES,dump

def main(tag):
    out=ROOT/'runs'/tag
    va=json.loads((out/'val_metrics.json').read_text());te=json.loads((out/'test_metrics.json').read_text())
    a=json.loads((out/'analysis.json').read_text())
    with open(out/'val_predictions.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    # Resample complete record groups, preserving correlated windows within each group.
    ar=[r for r in rows if r['label']=='A'];groups=sorted({r['group'] for r in ar})
    counts=np.array([[sum(r['prediction']=='A' for r in ar if r['group']==g),sum(r['group']==g for r in ar)] for g in groups])
    rng=np.random.default_rng(20261023);rates=[]
    if groups:
        for _ in range(2000):
            totals=counts[rng.integers(0,len(groups),size=len(groups))].sum(axis=0)
            rates.append(float(totals[0]/totals[1]))
    ci=np.quantile(rates,[.025,.975]).tolist() if rates else [None,None]
    dump(out/'A_group_bootstrap.json',{'seed':20261023,'iterations':2000,'record_groups_with_A':len(groups),
      'recall_percentile_95_interval':ci,'scope':'validation; complete record groups resampled; not patient-certified'})
    lines=['# 记录隔离基线结果','',f'运行：{tag}。最优第 {va["best_epoch"]} 轮。','',
      '这是原模型在新分组协议下的基线，不是新结构带来的提升。B 只有一个来源记录，验证和测试均无 B 支持，不能报告 B 独立泛化能力。','',
      '| 集合 | 准确率 | 有支持六类 macro-F1 | 固定七类 macro-F1 |',
      '|---|---:|---:|---:|']
    for s,m in [('验证',va),('测试',te)]:
        lines.append(f'| {s} | {m["accuracy"]:.2%} | {m["supported_macro_f1"]:.4f} | {m["report"]["macro avg"]["f1-score"]:.4f} |')
    lines+=['','## 测试集分类别结果','','| 类别 | 样本 | 精确率 | 召回率 | F1 |','|---|---:|---:|---:|---:|']
    for c in CLASSES:
        r=te['report'][c]
        label=c.replace('|', '\\|')
        if r['support']==0:lines.append(f'| {label} | 0 | 无法估计 | 无法估计 | 无法估计 |')
        else:lines.append(f'| {label} | {int(r["support"])} | {r["precision"]:.4f} | {r["recall"]:.4f} | {r["f1-score"]:.4f} |')
    lines+=['','## 验证集房早诊断','','| 分层 | A 窗口 | 检出 | 召回率 |','|---|---:|---:|---:|']
    for r in a['strata'][:5]:
        recall=f'{r["recall"]:.2%}' if r['recall'] is not None else '无样本'
        lines.append(f'| {r["stratum"]} | {r["n"]} | {r["detected_A"]} | {recall} |')
    lines+=['',f'验证集正常窗口 {a["normal_windows"]} 个，其中 {a["normal_false_A"]} 个误报为 A。',
      f'A 来自 {len(groups)} 个记录组。按记录组重采样的召回率 95% 描述区间：{ci}。记录身份尚不能完全替代受试者身份。',
      '', '单 A、多 A 的差异是相关性证据，仍需结合每条记录及波形检查，不能认定单一因果或性能上限。',
      '', '原随机窗口测试集 95.19% 与此处的记录隔离结果不是同条件比较，差异还包含并列标签规则和缺失窗口筛查变化。',
      '', '配置、数据校验、模型权重、逐窗口预测和训练历史均保存在本运行目录。测试集不用于选参数。']
    (out/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--tag',default='record_baseline_seed0');a=p.parse_args();main(a.tag)

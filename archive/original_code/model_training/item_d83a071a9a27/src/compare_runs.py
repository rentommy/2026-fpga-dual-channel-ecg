import json,csv
import numpy as np
from beat_project import ROOT,CLASSES,dump,sha

folders=[ROOT/'runs/beat_center_only_seed0',ROOT/'runs/beat_context_seed0']
arrays=[np.load(p/'sample_indices.npz') for p in folders]
for split in ('train','val','test'):assert np.array_equal(arrays[0][split],arrays[1][split])
for p in folders:
    c=json.loads((p/'config.json').read_text())
    assert c['manifest_sha256']==sha(ROOT/'data/manifest.json')
    assert c['code_sha256']==sha(p/'training_snapshot.py')
    assert c['model_sha256']==sha(p/'model_snapshot.py')
results=[]
for p in folders:
    c=json.loads((p/'config.json').read_text());v=json.loads((p/'val_metrics.json').read_text());t=json.loads((p/'test_metrics.json').read_text())
    for split,metrics in [('val',v),('test',t)]:assert sum(sum(r) for r in metrics['confusion_matrix'])==len(arrays[0][split])
    results.append({'name':p.name,'parameters':c['parameters'],'best_epoch':t['epoch'],'val_macro_f1':v['supported_macro_f1'],
      'test_macro_f1':t['supported_macro_f1'],'test_accuracy':t['accuracy'],'A':t['report']['A'],'R':t['report']['R']})
dump(ROOT/'runs/comparison.json',{'same_sample_indices':True,'source_snapshots_verified':True,'results':results,
  'caution':'single seed; paired task and split; annotation timing; unequal benefit across classes'})
lines=['# 本轮改进与同协议对照','','已按用户确认采用九类，原始 A/S、V/F 各自独立。',
  '', '本轮改了数据单位与模型结构；旧方案集中归档，新流程不再进行十秒窗口标签投票。',
  '', '## 数据与校验','','共提取 1,425,772 个标注候选，1,395,245 个可用目标。每个目标有独立原始标签、周期边界和来源记录。',
  '前/中心/后三个周期只是输入上下文，输出只针对中心。波形 256 点，独立 RR 分支保留时间信息。',
  '两次实验的训练、验证、测试索引逐项一致，数据和训练源码快照校验通过。',
  '', '| 模型 | 验证 macro-F1 | 测试 macro-F1 | 测试准确率 | A 精确率 | A 召回率 | A F1 |',
  '|---|---:|---:|---:|---:|---:|---:|']
for name,r in zip(['仅中心拍卷积对照','三拍上下文＋RR 新模型'],results):
    a=r['A'];lines.append(f'| {name} | {r["val_macro_f1"]:.4f} | {r["test_macro_f1"]:.4f} | {r["test_accuracy"]:.2%} | {a["precision"]:.2%} | {a["recall"]:.2%} | {a["f1-score"]:.4f} |')
lines+=['','macro-F1 均只统计有真实样本支持的八类，B 缺少独立测试来源。两次实验都先按验证集选点，再作最终测试，没有根据测试分数改超参。',
  '', '## 结论与尚未解决的问题','',
  '新模型在这一次固定划分和随机种子下提高了整体 macro-F1 和 A 类表现，但不是全面提升：R 类测试召回率由 54.24% 降至 0，L 类两者均为 0。',
  'S 类召回率提高但精确率仍只有约 3.48%，F 类仅 8 个测试样本。异常误报、少数类型识别和跨记录泛化仍是主要问题。',
  '测试 N 占约 95.5%，全猜 N 的单项准确率高于当前模型，不能仅凭 91.04% 准确率判断可用。应结合异常类别指标与误报；新模型当前不替换已有部署权重。',
  '标签和任务单位已改变，不能把旧十秒窗口指标与本轮逐拍指标直接相减。一次种子的增益也不能视为稳定收益。',
  '专家候选定位与后续心拍上下文仍属理想离线条件；自动检测误差、实时等待时间和板端推理尚未验证。',
  '', '## 文件位置','',
  '- `src/beat_project.py`：逐拍提取与训练入口。',
  '- `src/beat_model.py`：新残差卷积与 RR 模型、中心拍对照。',
  '- `data/beats.csv`：每拍标签、周期位置、记录来源与资格标记。',
  '- `data/单拍预处理样例.png`：九类单候选周期样例。',
  '- `runs/beat_context_seed0/`：新模型权重、配置、逐拍预测和报告。',
  '- `runs/beat_center_only_seed0/`：同协议中心拍对照。',
  '- `历史归档_10秒窗口方案_2026-10-24/`：旧方案全部文件与移动记录。',
  '', '下一轮应优先使用验证集检查 L/R 被误判成什么、RR 分支是否压制形态特征，以及来源记录偏差；随后开展多种子验证。当前测试结果保留作本轮结论，不作为下一轮调参依据。']
(ROOT/'本轮改进与结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))

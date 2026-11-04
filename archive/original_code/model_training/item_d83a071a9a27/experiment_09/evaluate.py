import json,csv
import numpy as np
import torch
from pipeline import ROOT,DATA,SOURCES,CLASSES,COMMON,arrays,model,metric,predict,save,sha

def main():
    torch.set_num_threads(8);d=arrays();manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'));records=manifest['records']
    assert json.loads((ROOT/'audit.json').read_text())['passed']
    for arm in ['two_db','six_db']:
        for seed in range(3):assert (ROOT/'runs'/f'{arm}_seed{seed}'/'complete.json').exists()
    selection=np.load(DATA/'selection_indices.npy');results=[];per_patient=[];checkpoint_audit=[]
    for arm in ['two_db','six_db']:
        for seed in range(3):
            folder=ROOT/'runs'/f'{arm}_seed{seed}';cfg=json.loads((folder/'config.json').read_text())
            assert cfg['manifest_sha256']==sha(DATA/'manifest.json')
            mu=np.array(cfg['rr_mean'],dtype=np.float32);sd=np.array(cfg['rr_std'],dtype=np.float32)
            m=model().cuda();m.load_state_dict(torch.load(folder/'best.pt',map_location='cuda',weights_only=True))
            p=predict(m,d,selection,mu,sd);assert np.array_equal(p,np.load(folder/'val_predictions.npy'))
            checkpoint_audit.append({'arm':arm,'seed':seed,'selection_predictions_reproduced':True})
            for splitname,split in [('val',1),('test',2)]:
                all_ix=np.flatnonzero(d['split']==split);all_pred=predict(m,d,all_ix,mu,sd)
                for db in ['all']+[v[0] for v in SOURCES]:
                    ids=[r['id'] for r in records if db=='all' or r['db']==db]
                    keep=np.isin(d['record'][all_ix],ids)
                    if not keep.any():continue
                    ix=all_ix[keep];pred=all_pred[keep];y=d['y'][ix];result=metric(y,pred)
                    result.update(arm=arm,seed=seed,db=db,split=splitname,n=len(y))
                    results.append(result)
                    if db!='all':
                        np.savez(folder/f'{db}_{splitname}_predictions.npz',indices=ix,predictions=pred)
                        for group in sorted({r['group'] for r in records if r['db']==db and r['split']==splitname}):
                            gids=[r['id'] for r in records if r['group']==group];gkeep=np.isin(d['record'][ix],gids)
                            if not gkeep.any():continue
                            for c,label in enumerate(CLASSES):
                                truth=(y==c)&gkeep;pp=(pred==c)&gkeep;tp=int((truth&pp).sum())
                                per_patient.append({'arm':arm,'seed':seed,'db':db,'split':splitname,'group':group,'label':label,
                                  'support':int(truth.sum()),'predicted':int(pp.sum()),'precision':tp/int(pp.sum()) if pp.any() else None,
                                  'recall':tp/int(truth.sum()) if truth.any() else None})
                print('evaluated',arm,seed,splitname,len(all_ix),flush=True)
    save(ROOT/'evaluation.json',results);save(ROOT/'checkpoint_audit.json',{'passed':True,'checks':checkpoint_audit})
    with (ROOT/'per_patient.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(per_patient[0]));w.writeheader();w.writerows(per_patient)
    report(results,manifest)

def report(results,manifest):
    lines=['# 六库完整接入对照结果','','使用0.5–40Hz双向带通＋50Hz Q30双向陷波、256Hz真实时间轴单拍、逐拍标准化、多尺度残差＋RR。恢复原始S，共八输出A/F/L/N/R/S/V/伪迹，S不改成A。',
           '对照为相同八输出网络、训练设置和固定选型验证子集的两库训练与六库训练；不是将七输出旧权重与八输出新权重直接比较。', '',
           '## 数据覆盖','','| 库 | 有人工参考标注的记录 | 训练记录 | 验证记录 | 测试记录 | 保留目标心拍数 |','|---|---:|---:|---:|---:|---:|']
    for db,_,_ in SOURCES:
        rows=[r for r in manifest['records'] if r['db']==db]
        lines.append(f"| {db} | {len(rows)} | {sum(r['split']=='train' for r in rows)} | {sum(r['split']=='val' for r in rows)} | {sum(r['split']=='test' for r in rows)} | {sum(r['n'] for r in rows):,} |")
    lines+=['','## 完整自然分布结果（三种子均值±标准差）','','| 训练方案 | 集合 | 准确率 | 八类macro-F1 | 全猜N准确率 |','|---|---|---:|---:|---:|']
    for arm in ['two_db','six_db']:
        for split in ['val','test']:
            for db in ['all','mit','edb','sddb','incart']:
                rr=[r for r in results if r['arm']==arm and r['split']==split and r['db']==db]
                if not rr:continue
                a=np.array([r['accuracy'] for r in rr]);f=np.array([r['macro_f1'] for r in rr])
                lines.append(f"| {arm} | {db}/{split} | {a.mean():.2%} ± {a.std():.2%} | {f.mean():.4f} ± {f.std():.4f} | {rr[0]['all_normal_accuracy']:.2%} |")
    lines+=['','## MIT原七类可比范围','','| 训练方案 | 集合 | 七类范围准确率 | 七类macro-F1 |','|---|---|---:|---:|']
    for arm in ['two_db','six_db']:
        for split in ['val','test']:
            rr=[r for r in results if r['arm']==arm and r['split']==split and r['db']=='mit']
            lines.append(f"| {arm} | MIT/{split} | {np.mean([r['common7_accuracy'] for r in rr]):.2%} | {np.mean([r['common7_macro_f1'] for r in rr]):.4f} |")
    lines+=['','MIT原七类范围只排除真实S，预测为S的其他真类仍计为错误。与旧轮次比较时须同时考虑网络输出、选型规则和训练轮定义已改变。', '',
            '## 六库方案逐类表现（三种子平均）','','| 集合 | 类别 | 精确率 | 召回率 | F1 | 样本数 |','|---|---|---:|---:|---:|---:|']
    for db,split in [('mit','val'),('all','test')]:
        rr=[r for r in results if r['arm']=='six_db' and r['db']==db and r['split']==split]
        for c in CLASSES:
            values=[np.mean([r['report'][c][k] for r in rr]) for k in ['precision','recall','f1-score']]
            label=c.replace('|','\\|');support=int(rr[0]['report'][c]['support'])
            if support:
                lines.append(f"| {db}/{split} | {label} | {values[0]:.2%} | {values[1]:.2%} | {values[2]:.4f} | {support} |")
            else:lines.append(f"| {db}/{split} | {label} | — | — | — | 0 |")
    inv=json.loads((ROOT/'inventory.json').read_text(encoding='utf-8'))
    lines+=['','## 解释与限制','',
      '- “完整”表示六库所有具备参考atr标注且可解析的记录均审核接入；每记录取一个明确记录的导联，缺首选导联时取第一导联，未只保留MLII/MLIII记录。',
      '- 猝死库有11条记录缺少人工参考atr（'+','.join(inv['summary']['sddb']['records_missing_atr'])+'），未把未审核ari自动标注当作监督真值。',
      '- B的54,725个原始标注集中在猝死库36号记录，另两库各仅1个B，仍不具备有意义的独立来源覆盖；本轮不训练B，也不将其改成L/R。',
      '- EDB按官方同患者关系合并分组，INCART沿用官方患者分组，MIT201/202同组；STDB与SVDB无法确认跨记录身份，均整库只用于训练，不报告这些库的独立测试。未知跨库身份和部分波形重叠仍未完全认证，不能声称绝对无患者泄漏。',
      '- SVDB此前作为外部库的身份已经改变，本轮纳入训练，不再称其为外部测试。已使用过的旧MIT/INCART测试也不包装成全新外部证据。',
      '- 为控制长Holter多数类的计算量，每轮180,000次训练抽取，按完整随机排列顺序循环；早停必须等所有纳入训练的心拍至少遍历一次，不删减长记录中的正常心拍。两方案每轮更新次数相同，最多24轮。',
      '- 模型按固定多库验证子集的八类macro-F1选取；该子集每库每类最多2000拍，只用于选型，上面的最终验证和测试表均使用完整自然分布。标准差是种子波动，不是患者总体置信区间。',
      '- 单库若没有某类别的真样本，逐类表显示横线；八类macro-F1仍将缺失类别计零，因此不直接比较不同库的绝对难度。合并测试的八类都有真样本，MIT原七类另有可比范围。',
      '- A和S保留各库原始符号，两者临床定义范围不同，跨库标注习惯可能影响可分性；没有通过改标签制造提升。',
      '- 使用专家定位、未来RR和双向滤波，尚未完成自动检测与实时FPGA验证。总体80%不替代逐类召回与精确率要求。',
      '- 另发现1107个目标的相邻标注间隔超过10秒，可能涉及长停搏、复杂节律或标注覆盖间断，当前按原始标注保留；时间特征标准化后截断到±8。它们是候选标注间隔，不能全部宣称已经验证为临床RR，详见rr_quality_note.json。',
      '- 参考：[EDB官方同患者说明](https://physionet.org/content/edb/1.0.0/)、[猝死库参考标注限制](https://physionet.org/content/sddb/1.0.0/)。',
      '- 审计见audit.json，重载权重复现检查见checkpoint_audit.json，逐患者结果见per_patient.csv。']
    (ROOT/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':main()

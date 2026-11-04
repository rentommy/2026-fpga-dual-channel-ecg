"""Evaluate fixed selected runs only after all declared development repeats finish."""
from pathlib import Path
import json,csv
import numpy as np
import torch
from run import ROOT,CLASSES,Network,metrics,save,sha
from normalize_study import normalize

def main():
    torch.set_num_threads(8)
    selection=json.loads((ROOT/'selection.json').read_text())
    winner=selection['winner'].rsplit('_seed',1)[0]
    names=list(dict.fromkeys(['baseline_mit','baseline_z_mit',winner]))
    with np.load(ROOT/'data/beats.npz') as archive:
        d={key:archive[key] for key in archive.files}
    datahash=sha(ROOT/'data/beats.npz')
    for name in names:
        for seed in range(3):assert (ROOT/'runs'/f'{name}_seed{seed}'/'complete.json').exists()
    results=[];patient_rows=[]
    device='cuda' if torch.cuda.is_available() else 'cpu'
    for name in names:
        for seed in range(3):
            folder=ROOT/'runs'/f'{name}_seed{seed}';cfg=json.loads((folder/'config.json').read_text())
            assert cfg['data_sha256']==datahash
            model=Network(cfg['kind']).to(device);model.load_state_dict(torch.load(folder/'best.pt',map_location=device,weights_only=True));model.eval()
            for db,split in [('mit','val'),('incart','val'),('incart','test'),('svdb','external')]:
                ix=np.flatnonzero((d['db']==db)&(d['split']==split));pred=[]
                with torch.no_grad():
                    for batch in np.array_split(ix,max(1,int(np.ceil(len(ix)/512)))):
                        x=d['x'][batch].copy()
                        if cfg.get('normalization')=='per_beat_valid_mean_std':x=normalize(x)
                        else:x[:,0]/=cfg['scale']
                        r=np.clip((d['r'][batch]-cfg['rr_mean'])/cfg['rr_std'],-8,8).astype(np.float32)
                        pred.extend(model(torch.tensor(x,device=device),torch.tensor(r,device=device)).argmax(1).cpu().tolist())
                pred=np.array(pred);y=d['y'][ix];result=metrics(y,pred)
                if db=='mit' and split=='val':
                    assert np.array_equal(pred,np.load(folder/'val_predictions.npy')), 'Saved weights do not reproduce validation predictions'
                support=np.bincount(y,minlength=7);present=np.flatnonzero(support)
                result['macro_f1_supported']=float(np.mean([result['report'][CLASSES[c]]['f1-score'] for c in present]))
                result.update(name=name,seed=seed,dataset=db,split=split,samples=len(y),supported_classes=[CLASSES[c] for c in present],all_normal_accuracy=float((y==CLASSES.index('N')).mean()))
                results.append(result)
                np.savez(folder/f'{db}_{split}_predictions.npz',indices=ix,predictions=pred)
                for g in np.unique(d['group'][ix]):
                    keep=d['group'][ix]==g
                    row={'model':name,'seed':seed,'dataset':db,'split':split,'group':g,'samples':int(keep.sum()),'accuracy':float((y[keep]==pred[keep]).mean())}
                    for c in range(7):
                        truth=keep&(y==c);pp=keep&(pred==c);tp=int((truth&pp).sum())
                        row[CLASSES[c]+'_support']=int(truth.sum());row[CLASSES[c]+'_recall']=tp/int(truth.sum()) if truth.any() else None
                        row[CLASSES[c]+'_precision']=tp/int(pp.sum()) if pp.any() else None
                    patient_rows.append(row)
                print(name,seed,db,split,result['accuracy'],result['macro_f1'],flush=True)
    save(ROOT/'evaluation.json',results)
    with (ROOT/'per_patient.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(patient_rows[0]));w.writeheader();w.writerows(patient_rows)
    lines=['# 第七轮：真实时间轴、新结构与新增患者', '',
           '七输出仍为A/F/L/N/R/V/伪迹。S没有改为A，B没有改为R。SVDB未用于训练。', '',
           '## 同口径开发对照（seed0，含后续追加标准化对照）', '',
           '| 模型 | MIT验证准确率 | MIT验证macro-F1 |', '|---|---:|---:|']
    for name in selection['scores']:
        m=json.loads((ROOT/'runs'/name/'val_metrics.json').read_text())
        lines.append(f"| {name} | {m['accuracy']:.2%} | {m['macro_f1']:.4f} |")
    lines += ['', '## 上一轮结果供整体方案比较', '', '| 方案 | MIT验证准确率三种子均值 | macro-F1三种子均值 |', '|---|---:|---:|']
    for oldname in ['baseline','balanced_all']:
        old=[json.loads((ROOT.parent/'study_05/runs'/f'{oldname}_seed{s}'/'val_metrics.json').read_text()) for s in range(3)]
        lines.append(f"| study_05/{oldname} | {np.mean([v['accuracy'] for v in old]):.2%} | {np.mean([v['macro_f1'] for v in old]):.4f} |")
    lines.append('\n这些是相同MIT开发患者上的整体方案比较；输入表示等多项因素不同，不作单因素归因。')
    lines += ['',f'按预定MIT验证macro-F1选出的候选为 **{winner}**。不是根据外部测试挑选。', '',
              '## 三种子复核及外部评估', '',
              '| 模型 | 数据集 | 准确率均值±种子标准差 | 七类macro-F1均值 | 有样本类别macro-F1均值 |', '|---|---|---:|---:|---:|']
    for name in names:
        for db,split in [('mit','val'),('incart','val'),('incart','test'),('svdb','external')]:
            rr=[v for v in results if v['name']==name and v['dataset']==db and v['split']==split]
            ac=np.array([v['accuracy'] for v in rr]);mf=np.mean([v['macro_f1'] for v in rr]);sf=np.mean([v['macro_f1_supported'] for v in rr])
            lines.append(f'| {name} | {db}/{split} | {ac.mean():.2%} ± {ac.std():.2%} | {mf:.4f} | {sf:.4f} |')
    lines += ['', '## 多数类基线与实际覆盖', '', '| 集合 | 保留样本数 | 全猜N准确率 | 存在的目标类别 |', '|---|---:|---:|---|']
    for db,split in [('mit','val'),('incart','val'),('incart','test'),('svdb','external')]:
        v=next(v for v in results if v['dataset']==db and v['split']==split)
        labels=','.join(v['supported_classes']).replace('|','伪迹')
        lines.append(f"| {db}/{split} | {v['samples']} | {v['all_normal_accuracy']:.2%} | {labels} |")
    lines += ['', '标准差反映训练随机性，不是患者总体置信区间。外部集合不存在的类别不能据其分数声称已验证；七类macro-F1会将无支持类别计零，另列有支持类别均值便于解释。', '',
              '## MIT验证逐类表现（三种子平均）', '', '| 模型 | 类别 | 精确率 | 召回率 | F1 |', '|---|---|---:|---:|---:|']
    for name in names:
        rr=[v for v in results if v['name']==name and v['dataset']=='mit']
        for c in CLASSES:
            p,r,f=[np.mean([v['report'][c][key] for v in rr]) for key in ['precision','recall','f1-score']]
            label=c.replace('|','\\|');lines.append(f'| {name} | {label} | {p:.2%} | {r:.2%} | {f:.4f} |')
    lines += ['', '## 数据与限制', '',
              '- MIT保持原患者分组，201/202同组，旧MIT测试未评估。INCART按患者冻结20训练/6验证/6测试；SVDB整体外部评估，但其唯一患者身份未知。',
              '- 只对七类内且切分有效的目标评估。SVDB中大量S等非目标心拍被排除；外部准确率不代表全部心拍识别能力。具体排除及覆盖见data/manifest.json。',
              '- 数据输入：256Hz、205点、中心77，0.5–40Hz滤波、抗混叠重采样、中点约束、补零掩码；普通配置采用训练集全局幅值尺度，带_z_配置采用有效点逐拍均值/标准差。没有逐拍时间拉伸。',
              '- 标准化对照是观察第一阶段开发结果后的追加研究，不是最初预注册的六组；选型始终只使用MIT开发验证，结果存在反复使用开发集的乐观偏差。',
              '- 真心拍RR序列排除伪迹。伪迹候选使用到左右真心拍的距离作为上下文，不作为真RR插入序列，也没有用目标标签直接生成零向量作为类别提示。',
              '- 当前依赖专家心拍位置，使用未来间期和零相位滤波；未验证实时检测或FPGA部署。INCART尚未做局部重新对齐。',
              '- 改变了输入、采样率和幅值表示，因此与study_05的跨轮差值不是单独修复RR的因果收益；本轮内部同数据结构对照才可比较。',
              '- 混合训练每轮样本更多，优化步数也更多；这是完整训练方案的比较，并非严格固定计算量的数据增益实验。',
              '- 模板网络是受论文启发的可训练局部模板实现，不是论文原版复现；模板只从训练患者提取，索引保存在配置中。',
              '- 所有真实原始文件不变，旧实验不覆盖。新权重未自动替换部署权重。', '',
              '总体准确率80%为目标；应同时检查逐类召回、精确率和患者结果，不能靠多数类达标认定任务已完成。']
    (ROOT/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':main()

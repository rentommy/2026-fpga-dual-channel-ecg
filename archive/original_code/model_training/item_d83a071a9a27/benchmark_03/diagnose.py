"""Post-training diagnostics; no fitting, no configuration selection."""
import json
import numpy as np
import torch
from benchmark import ROOT, CLASSES, load, indices, metrics, dump, sha, table
from models import AlignedCNN

torch.set_num_threads(8)
d=load()
name=json.loads((ROOT/'selection.json').read_text())['selected_cnn']
folder=ROOT/'runs'/f'{name}_seed0'
c=json.loads((folder/'config.json').read_text())
device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
m=AlignedCNN(c['use_rr']).to(device)
m.load_state_dict(torch.load(folder/'best.pt',map_location=device,weights_only=True)['model'])
m.eval()
tr=indices(d,'train')
rr=np.clip((d['rr'][tr]-np.array(c['rr_mean']))/np.array(c['rr_std']),-8,8).astype('float32')
pred=[]
with torch.no_grad():
    for start in range(0,len(tr),256):
        ix=tr[start:start+256]
        logits=m(torch.tensor(d[c['mode']][ix],device=device),torch.tensor(rr[start:start+256],device=device))
        pred.extend(logits.argmax(1).cpu().tolist())
train=metrics(d['labels'][tr],np.array(pred))
dump(folder/'train_diagnostic_metrics.json',train)
val=json.loads((folder/'val_metrics.json').read_text())
manifest=json.loads((ROOT/'data/manifest.json').read_text())
rows=[]
vp=np.load(folder/'val_predictions.npy');va=indices(d,'val')
for rid in np.unique(d['record'][va]):
    for j,cls in enumerate(CLASSES):
        keep=(d['record'][va]==rid)&(d['labels'][va]==j)
        if not keep.any():continue
        counts=np.bincount(vp[keep],minlength=9)
        rows.append({'record':manifest['records'][int(rid)]['record'],'class':cls,'support':int(keep.sum()),
            'recall':float((vp[keep]==j).mean()),'most_predicted':CLASSES[counts.argmax()]})
table(ROOT/'validation_record_diagnostics.csv',rows)
checks=[]
for config in sorted((ROOT/'runs').glob('*_seed*/config.json')):
    cfg=json.loads(config.read_text());p=config.parent
    assert cfg['data_sha256']==manifest['array_sha256']
    assert cfg['code_sha256']==sha(p/'training_snapshot.py')
    assert cfg['model_sha256']==sha(p/'model_snapshot.py')==sha(ROOT/'models.py')
    checks.append(p.name)
dump(ROOT/'snapshot_audit.json',{'verified_runs':checks,'passed':True})
lines=['# 验证集失败定位','','以下定位仅用训练/验证，未据此重选模型。训练分数来自验证集选定的 seed0 最佳权重。','',
       '| 原始标签 | 训练召回率 | 验证召回率 | 验证最常误判为 | 该误判拍数 |','|---|---:|---:|---|---:|']
for j,cls in enumerate(CLASSES):
    t=train['report'][cls];v=val['report'][cls];cm=np.array(val['confusion_matrix'][j]);cm[j]=0
    label=cls.replace('|','\\|');target=CLASSES[cm.argmax()].replace('|','\\|') if cm.sum() else '无'
    ts=f'{t["recall"]:.2%}' if t['support'] else '无样本';vs=f'{v["recall"]:.2%}' if v['support'] else '无样本'
    lines.append(f'| {label} | {ts} | {vs} | {target} | {cm.max()} |')
lines+=['','逐记录结果见 `validation_record_diagnostics.csv`。训练/验证落差提示泛化不足，但不能仅凭落差判定是哪一种生理或设备因素造成。',
    'L 在训练中仅来自两个受试者组、验证中仅一个；R 在训练中仅两个受试者组。大量相似心拍不能替代独立受试者覆盖。',
    'B 在本库没有训练样本；原始 S 只有同一记录的两拍。保持九个输出节点不等于已经能训练和验证九类。']
(ROOT/'验证失败定位.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Diagnostic complete; snapshot audit passed.',flush=True)

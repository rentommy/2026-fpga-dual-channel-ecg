"""Predeclared development studies; no old-test evaluation."""
from pathlib import Path
import csv,json,hashlib,shutil,random,time,argparse
import numpy as np
import torch
from torch import nn
from sklearn.metrics import classification_report,confusion_matrix,f1_score
from baseline_model import BeatModel
ROOT=Path(__file__).resolve().parent
CLASSES=['A','F','L','N','R','V','|'];OLD=['A','B','F','L','N','R','S','V','|']
CONFIGS={
 'baseline':dict(weighted=True),
 'uniform':dict(weighted=False),
 'balanced':dict(weighted=False,sample=True),
 'balanced_shift':dict(weighted=False,sample=True,augment='shift'),
 'balanced_scale':dict(weighted=False,sample=True,augment='scale'),
 'balanced_noise':dict(weighted=False,sample=True,augment='noise'),
 'balanced_all':dict(weighted=False,sample=True,augment='all'),
 'morph_only':dict(weighted=True,mode='morph_only'),
 'rr_only':dict(weighted=True,mode='rr_only'),
 'feature_fusion':dict(weighted=True,mode='feature_fusion')}
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def table(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def physical_features(x):
    """Local +/-150ms descriptive features, NOT clinical QRS delineation."""
    z=x[:,0,54:163];mask=x[:,1,54:163];valid=mask.sum(1).clip(1)
    mx=np.where(mask,z,-np.inf).max(1);mn=np.where(mask,z,np.inf).min(1)
    delta=np.diff(z,axis=1);pairs=mask[:,1:]*mask[:,:-1];delta=delta*pairs
    energy=z*z*mask;total=energy.sum(1)+1e-8;cdf=np.cumsum(energy,1)/total[:,None]
    # Width of central 80% energy in this fixed region; not QRS onset/offset.
    width=((cdf>=.9).argmax(1)-(cdf>=.1).argmax(1))/360
    peak=np.argmax(np.where(mask,np.abs(z),-1),axis=1)
    pos=(np.arange(z.shape[1])-54)/360
    return np.stack([mx,mn,mx-mn,delta.max(1)*360,delta.min(1)*360,
      np.sqrt(total/valid),width,(peak-54)/360,(energy*pos).sum(1)/total,
      valid/z.shape[1]],axis=1).astype('float32')

def sampling_weights(y,groups):
    """P(class) proportional sqrt(count), then uniform patient within class."""
    w=np.zeros(len(y),dtype='float64')
    for c in np.unique(y):
        ix=y==c;gs=np.unique(groups[ix])
        for g in gs:
            keep=ix&(groups==g);w[keep]=np.sqrt(ix.sum())/(len(gs)*keep.sum())
    return w/w.sum()

def augment(x,mode):
    if not mode:return x
    x=x.clone()
    if mode in ('shift','all'):
        # Zero-padded translation; no wrap and no import of adjacent beats.
        shift=torch.randint(-3,4,(len(x),1),device=x.device)
        positions=torch.arange(x.shape[-1],device=x.device)[None,:]-shift
        valid=(positions>=0)&(positions<x.shape[-1]);idx=positions.clamp(0,x.shape[-1]-1)
        x=torch.gather(x,2,idx[:,None,:].expand(-1,2,-1))*valid[:,None,:]
    if mode in ('scale','all'):x[:,0]*=torch.empty((len(x),1),device=x.device).uniform_(.9,1.1)
    if mode in ('noise','all'):x[:,0]+=torch.randn_like(x[:,0])*.02*x[:,1]
    x[:,0]*=x[:,1]
    return x

class Model(nn.Module):
    def __init__(self,mode='full'):
        super().__init__();self.mode=mode
        if mode=='rr_only':self.net=nn.Sequential(nn.Linear(8,32),nn.ReLU(),nn.Dropout(.2),nn.Linear(32,7))
        else:
            self.core=BeatModel('se_gru')
            if mode=='feature_fusion':
                self.extra=nn.Sequential(nn.Linear(10,16),nn.ReLU());self.core.head=nn.Linear(96,7)
    def forward(self,x,r,f):
        if self.mode=='rr_only':return self.net(r)
        if self.mode=='morph_only':return self.core(x,torch.zeros_like(r))
        if self.mode!='feature_fusion':return self.core(x,r)
        z=self.core.conv(x);z=self.core.temporal(z.transpose(1,2))[1][-1]
        return self.core.head(torch.cat([self.core.morph(z),self.core.rr(r),self.extra(f)],1))

def data():
    source=ROOT.parent/'benchmark_03/data/beats.npz';d=np.load(source)
    lookup=np.array([CLASSES.index(c) if c in CLASSES else -1 for c in OLD]);y=lookup[d['labels']]
    ix={s:np.flatnonzero((d['split']==v)&(y>=0)) for s,v in [('train',0),('val',1)]}
    # Only development rows enter this study. Old test arrays are never evaluated.
    meta=list(csv.DictReader((ROOT.parent/'benchmark_03/data/beats.csv').open(encoding='utf-8-sig')))
    sets={s:{'index':i,'x':d['warped'][i],'r':d['rr'][i],'f':physical_features(d['physical'][i]),'y':y[i],
       'group':np.array([meta[j]['group'] for j in i]),'record':np.array([meta[j]['record'] for j in i])} for s,i in ix.items()}
    assert not(set(sets['train']['group'])&set(sets['val']['group']))
    for key in ['r','f']:
        mu=sets['train'][key].mean(0);sd=sets['train'][key].std(0)+1e-6
        for s in sets:sets[s][key]=np.clip((sets[s][key]-mu)/sd,-8,8).astype('float32')
        sets['train'][key+'_stats']={'mean':mu.tolist(),'std':sd.tolist()}
    return sets

def metric(y,p):
    return {'accuracy':float(np.mean(y==p)),'macro_f1':float(f1_score(y,p,labels=range(7),average='macro',zero_division=0)),
      'report':classification_report(y,p,labels=range(7),target_names=CLASSES,output_dict=True,zero_division=0),
      'confusion_matrix':confusion_matrix(y,p,labels=range(7)).tolist()}

def fit(name,seed,sets):
    torch.set_num_threads(8);torch.manual_seed(seed);random.seed(seed);np.random.seed(seed)
    cfg=CONFIGS[name];out=ROOT/'runs'/f'{name}_seed{seed}';out.mkdir(parents=True,exist_ok=False)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tensors={s:{k:torch.tensor(v[k],device=device) for k in ['x','r','f','y']} for s,v in sets.items()}
    tr=sets['train'];counts=np.bincount(tr['y'],minlength=7);w=np.clip(np.sqrt(counts.max()/counts),1,12);w/=w.mean()
    loss_fn=nn.CrossEntropyLoss(weight=torch.tensor(w,dtype=torch.float32,device=device) if cfg['weighted'] else None)
    sw=sampling_weights(tr['y'],tr['group']);sw_tensor=torch.tensor(sw,device=device)
    m=Model(cfg.get('mode','full')).to(device);opt=torch.optim.AdamW(m.parameters(),lr=.001,weight_decay=.01)
    save(out/'config.json',{'name':name,'seed':seed,**cfg,'classes':CLASSES,'parameters':sum(p.numel() for p in m.parameters()),'rr_stats':tr['r_stats'],'feature_stats':tr['f_stats'],'code_sha256':sha(ROOT/'study.py'),'model_sha256':sha(ROOT/'baseline_model.py'),'protocol_sha256':sha(ROOT/'protocol.json')})
    shutil.copy2(ROOT/'study.py',out/'training_snapshot.py');shutil.copy2(ROOT/'baseline_model.py',out/'model_snapshot.py')
    best=-1;wait=0;history=[];sample_audit=[]
    for epoch in range(1,26):
        start=time.time();m.train();t=tensors['train'];n=len(t['y'])
        order=torch.multinomial(sw_tensor,n,replacement=True) if cfg.get('sample') else torch.randperm(n,device=device)
        if epoch==1:
            actual=np.bincount(order.cpu().numpy(),minlength=n)
            for c in range(7):
                for g in np.unique(tr['group'][tr['y']==c]):
                    keep=(tr['y']==c)&(tr['group']==g);sample_audit.append({'class':CLASSES[c],'group':g,'original':int(keep.sum()),'first_epoch_draws':int(actual[keep].sum()),'expected_draws':float(sw[keep].sum()*n) if cfg.get('sample') else int(keep.sum())})
            table(out/'sampling_audit.csv',sample_audit)
        total=0
        for batch in order.split(256):
            opt.zero_grad(set_to_none=True);x=augment(t['x'][batch],cfg.get('augment'))
            loss=loss_fn(m(x,t['r'][batch],t['f'][batch]),t['y'][batch]);loss.backward();nn.utils.clip_grad_norm_(m.parameters(),5);opt.step();total+=loss.item()*len(batch)
        m.eval();t=tensors['val'];pred=[]
        with torch.no_grad():
            for j in range(0,len(t['y']),256):pred.extend(m(t['x'][j:j+256],t['r'][j:j+256],t['f'][j:j+256]).argmax(1).cpu().tolist())
        result=metric(sets['val']['y'],np.array(pred));score=result['macro_f1']
        history.append({'epoch':epoch,'train_loss':total/n,'val_macro_f1':score,'seconds':time.time()-start});save(out/'history.json',history)
        print(name,seed,history[-1],flush=True)
        if score>best:
            best=score;wait=0;torch.save(m.state_dict(),out/'best.pt');result['epoch']=epoch;save(out/'val_metrics.json',result);np.save(out/'val_predictions.npy',pred)
        else:wait+=1
        if wait>=6:break
    pred=np.load(out/'val_predictions.npy');rows=[];v=sets['val']
    for g in np.unique(v['group']):
        for c in range(7):
            group=v['group']==g;tp=int(((v['y']==c)&(pred==c)&group).sum());support=int(((v['y']==c)&group).sum());pp=int(((pred==c)&group).sum())
            rows.append({'group':g,'class':CLASSES[c],'support':support,'predicted':pp,'precision':tp/pp if pp else None,'recall':tp/support if support else None})
    table(out/'per_patient.csv',rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['run','report']);a=p.parse_args()
    if a.stage=='report':report();return
    if (ROOT/'protocol.json').exists():raise SystemExit('Existing frozen protocol; refusing overwrite')
    save(ROOT/'protocol.json',{'classes':CLASSES,'configs':CONFIGS,'epochs':25,'patience':6,'batch':256,'learning_rate':.001,'weight_decay':.01,'sampling':'sqrt class counts, uniform patient conditional on class; replacement; unweighted loss','augmentation':'shift +/-3 normalized samples; scale .9-1.1; noise sd .02; only training; no extra-feature fusion with augmentation','features':'10 fixed real-time local descriptive features; energy width is not clinical QRS duration','selection':'max validation macro-F1 at seed0; repeat baseline and selected seeds1,2 without choosing seed','source_sha256':sha(ROOT.parent/'benchmark_03/data/beats.npz'),'test':'none; development validation reused; no fresh holdout claim','budget':'10 seed0 configs then 2 seeds each for baseline and winner'})
    sets=data()
    for name in CONFIGS:fit(name,0,sets)
    scores={n:json.loads((ROOT/'runs'/f'{n}_seed0/val_metrics.json').read_text())['macro_f1'] for n in CONFIGS}
    selected=max(scores,key=scores.get);save(ROOT/'selection.json',{'scores':scores,'selected':selected,'basis':'development validation only'})
    for name in dict.fromkeys(['baseline',selected]):
        for seed in [1,2]:fit(name,seed,sets)
    report()

def report():
    selected=json.loads((ROOT/'selection.json').read_text())['selected'];rows=[]
    for p in sorted((ROOT/'runs').glob('*/val_metrics.json')):
        c=json.loads((p.parent/'config.json').read_text());r=json.loads(p.read_text());row={'name':c['name'],'seed':c['seed'],'accuracy':r['accuracy'],'macro_f1':r['macro_f1']}
        for label in CLASSES:
            for k in ['precision','recall','f1-score']:row[label+'_'+k]=r['report'][label][k]
        rows.append(row)
    table(ROOT/'summary.csv',rows)
    lines=['# 第五轮：五项改进的开发验证','','七输出：A/F/L/N/R/V/|。旧测试未评估；以下仅为反复使用的开发验证成绩，不能当作独立测试。','','| 单种子方案 | 准确率 | macro-F1 | A 精确率 | A 召回率 | L 召回率 | R 召回率 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['seed']==0:lines.append(f'| {r["name"]} | {r["accuracy"]:.2%} | {r["macro_f1"]:.4f} | {r["A_precision"]:.2%} | {r["A_recall"]:.2%} | {r["L_recall"]:.2%} | {r["R_recall"]:.2%} |')
    lines+=['',f'预定规则选择：{selected}。对照关系：baseline↔uniform 检查损失权重；uniform↔balanced 检查采样；balanced↔三个单项增强检查各增强；baseline↔morph_only/rr_only 检查输入信息；baseline↔feature_fusion 检查显式形态特征。balanced_all 是预先列入的组合实验。',
      '', '| 三种子配置 | macro-F1 均值 | 种子标准差 | A 召回均值 | L 召回均值 | R 召回均值 |','|---|---:|---:|---:|---:|---:|']
    summary={}
    for name in dict.fromkeys(['baseline',selected]):
        subset=[r for r in rows if r['name']==name];scores=[r['macro_f1'] for r in subset]
        summary[name]={'seeds':[r['seed'] for r in subset],'macro_f1_mean':float(np.mean(scores)),'macro_f1_std':float(np.std(scores))}
        lines.append(f'| {name} | {np.mean(scores):.4f} | {np.std(scores):.4f} | {np.mean([r["A_recall"] for r in subset]):.2%} | {np.mean([r["L_recall"] for r in subset]):.2%} | {np.mean([r["R_recall"] for r in subset]):.2%} |')
    save(ROOT/'repeat_summary.json',summary)
    lines+=['','标准差只反映本次三个训练种子，不是受试者置信区间，也不替代多个受试者划分。每位受试者和每个类别的分数见各运行目录 per_patient.csv。',
      '全体方案使用相同中心标签、同一受试者划分。采样和增强仅用于训练；RR/形态特征缩放仅拟合训练。形态分支消融通过将 RR 输入置零实现，保留网络容量；RR-only 使用独立小 MLP，既改变输入也改变容量，不能将差值全部归因于某一类信息。',
      '手工形态特征取原时间轴中心前后约150ms区域，包括幅值、斜率、能量宽度等描述量；能量宽度不是经过人工验证的 QRS 起止时长。',
      '没有使用波形翻转、邻拍标签或测试成绩选配置。当前仍为专家候选定位、离线滤波与后续 RR 条件。']
    (ROOT/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':main()

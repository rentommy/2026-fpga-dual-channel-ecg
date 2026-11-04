"""Adaptive follow-up declared before any external evaluation: normalization ablation."""
import json,random,time,shutil
import numpy as np
import torch
from torch import nn
from run import ROOT,Network,CLASSES,metrics,save,sha

def fit(kind,mixed,seed):
    name=f'{kind}_z_'+('mixed' if mixed else 'mit')+f'_seed{seed}';out=ROOT/'runs'/name
    if (out/'complete.json').exists():return
    out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(8);torch.manual_seed(seed);np.random.seed(seed);random.seed(seed)
    with np.load(ROOT/'data/beats.npz') as archive:d={k:archive[k] for k in archive.files}
    tr=np.flatnonzero((d['split']=='train')&((d['db']!='svdb') if mixed else (d['db']=='mit')))
    va=np.flatnonzero((d['split']=='val')&(d['db']=='mit'))
    mu=d['r'][tr].mean(0);sd=d['r'][tr].std(0)+1e-6;device='cuda'
    def tensors(ix):
        x=normalize(d['x'][ix]);r=np.clip((d['r'][ix]-mu)/sd,-8,8).astype(np.float32)
        return [torch.tensor(a,device=device) for a in [x,r,d['y'][ix]]]
    tx,rr,y=tensors(tr);vx,vr,vy=tensors(va)
    model=Network(kind).to(device);counts=np.bincount(d['y'][tr],minlength=7)
    weights=np.clip(np.sqrt(counts.max()/counts),1,12);weights/=weights.mean()
    loss_fn=nn.CrossEntropyLoss(weight=torch.tensor(weights,dtype=torch.float32,device=device))
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    save(out/'config.json',{'kind':kind,'mixed':mixed,'seed':seed,'normalization':'per_beat_valid_mean_std','scale':1,
         'rr_mean':mu.tolist(),'rr_std':sd.tolist(),'classes':CLASSES,'train_counts':counts.tolist(),
         'data_sha256':sha(ROOT/'data/beats.npz'),'code_sha256':sha(ROOT/'normalize_study.py'),
         'model_code_sha256':sha(ROOT/'run.py'),'parameters':sum(p.numel() for p in model.parameters())})
    shutil.copy2(__file__,out/'code_snapshot.py');shutil.copy2(ROOT/'run.py',out/'model_snapshot.py')
    best=-1;wait=0;history=[]
    for epoch in range(1,31):
        start=time.time();model.train();total=0
        for ix in torch.randperm(len(y),device=device).split(256):
            opt.zero_grad(set_to_none=True);loss=loss_fn(model(tx[ix],rr[ix]),y[ix]);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);opt.step();total+=float(loss.detach())*len(ix)
        model.eval()
        with torch.no_grad():pred=torch.cat([model(vx[i:i+512],vr[i:i+512]).argmax(1) for i in range(0,len(vy),512)]).cpu().numpy()
        result=metrics(d['y'][va],pred);score=result['macro_f1']
        history.append({'epoch':epoch,'loss':total/len(y),'macro_f1':score,'accuracy':result['accuracy'],'seconds':time.time()-start})
        save(out/'history.json',history);print(name,history[-1],flush=True)
        if score>best:
            best=score;wait=0;torch.save(model.state_dict(),out/'best.pt');save(out/'val_metrics.json',result);np.save(out/'val_predictions.npy',pred)
        else:wait+=1
        if wait>=7:break
    save(out/'complete.json',{'best_macro_f1':best,'epochs':epoch})

def normalize(x):
    x=x.copy();mask=x[:,1];n=mask.sum(1).clip(1);mean=(x[:,0]*mask).sum(1)/n
    z=(x[:,0]-mean[:,None])*mask;std=np.sqrt((z*z).sum(1)/n).clip(1e-6)
    x[:,0]=z/std[:,None];return x

def main():
    save(ROOT/'normalization_protocol.json',{'reason':'Adaptive development follow-up after global-scale validation was poor; not an originally predeclared ablation',
         'configs':['baseline_z_mit','multi_z_mit','baseline_z_mixed','multi_z_mixed'],
         'selection':'merge all seed0 MIT validation scores, repeat final winner seeds1/2; external datasets remain untouched',
         'changed':'valid-sample per-beat mean/std only; same network, RR, loss, epochs and split'})
    previous=json.loads((ROOT/'selection.json').read_text());save(ROOT/'selection_phase1.json',previous)
    for mixed in [False,True]:
        for kind in ['baseline','multi']:fit(kind,mixed,0)
    candidates={p.parent.name:json.loads(p.read_text())['best_macro_f1'] for p in (ROOT/'runs').glob('*seed0/complete.json')}
    winner=max(candidates,key=candidates.get)
    save(ROOT/'selection.json',{'winner':winner,'scores':candidates,'adaptive_followup':True})
    for seed in [1,2]:fit('baseline',False,seed)
    if '_z_' in winner and not winner.startswith('baseline_z_mit_'):
        kind,_,domain,_=winner.split('_')
        for seed in [1,2]:fit(kind,domain=='mixed',seed)
    print('NORMALIZATION_COMPLETE',flush=True)

if __name__=='__main__':main()

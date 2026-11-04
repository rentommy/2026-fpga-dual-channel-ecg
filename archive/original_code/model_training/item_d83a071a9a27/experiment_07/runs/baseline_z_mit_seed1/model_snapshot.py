"""Frozen seven-output, physical-time, patient-separated ECG experiment."""
from pathlib import Path
import json,csv,collections,hashlib,shutil,sys,time,random,argparse
import numpy as np
import wfdb
from scipy.signal import butter,sosfiltfilt,resample_poly
import torch
from torch import nn
from sklearn.metrics import classification_report,confusion_matrix,f1_score

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
SAMPLES=PROJECT.parent/'样本'
CLASSES=['A','F','L','N','R','V','|']
BEATS=set('NLRaVFJASEj/QBenfr')
FS=256; PRE=77; LENGTH=205
sys.path.insert(0,str(PROJECT/'study_05'))
from baseline_model import BeatModel

def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare():
    out=ROOT/'data';out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise RuntimeError('Frozen data exists')
    old=list(csv.DictReader((PROJECT/'benchmark_03/data/beats.csv').open(encoding='utf-8-sig')))
    mit_split={r['record']:r['split'] for r in old}
    inc=SAMPLES/'incartdb-1.0.0';patients={};group=None
    for line in (inc/'files-patients-diagnoses.txt').read_text().splitlines():
        if line.startswith('patient '):group=line.strip().replace(' ','_')
        elif line.startswith('I'):
            for r in line.split():patients[r]=group
    groups=sorted(set(patients.values()));np.random.default_rng(2026102407).shuffle(groups)
    inc_split={g:('test' if i<6 else 'val' if i<12 else 'train') for i,g in enumerate(groups)}
    save(out/'split.json',{'mit':mit_split,'incart':inc_split,'svdb':'external whole database; patient identity unknown'})
    sources=[('mit',PROJECT.parent/'项目复现/ECG_ren/mit-bih-arrhythmia-database-1.0.0','MLII'),
             ('incart',inc,'II'),('svdb',SAMPLES/'svdb-1.0.0','ECG1')]
    exclusions=collections.Counter();rows=[];xs=[];rs=[];ys=[];checks=[];seen={}
    for db,folder,lead in sources:
        for rec in (folder/'RECORDS').read_text().splitlines():
            base=folder/rec;h=wfdb.rdheader(str(base))
            if lead not in h.sig_name:exclusions[db+':missing_lead']+=1;continue
            split=mit_split[rec] if db=='mit' else inc_split[patients[rec]] if db=='incart' else 'external'
            patient=('201+202' if rec in ['201','202'] else rec) if db=='mit' else patients[rec] if db=='incart' else rec
            group=db+':'+patient
            raw=wfdb.rdrecord(str(base),channels=[h.sig_name.index(lead)]).p_signal[:,0]
            assert np.isfinite(raw).all()
            fingerprint=hashlib.sha256(raw.tobytes()).hexdigest()
            assert fingerprint not in seen,('duplicate full waveform',rec,seen.get(fingerprint))
            seen[fingerprint]=db+':'+rec
            filtered=sosfiltfilt(butter(3,[.5,40],fs=h.fs,btype='bandpass',output='sos'),raw)
            signal=resample_poly(filtered,FS,int(h.fs))
            ann=wfdb.rdann(str(base),'atr')
            valid=(ann.sample>=0)&(ann.sample<h.sig_len)
            exclusions[db+':out_of_bounds']+=int((~valid).sum())
            pick=valid & np.array([s in BEATS for s in ann.symbol])
            times=ann.sample[pick]/h.fs
            assert np.all(np.diff(times)>0)
            # Physiological timing stream explicitly excludes artifact and rhythm/quality marks.
            for ai,(original,sym) in enumerate(zip(ann.sample,ann.symbol)):
                if not valid[ai]:continue
                if sym not in CLASSES:
                    exclusions[db+':symbol:'+sym]+=1;continue
                t=original/h.fs;j=int(np.searchsorted(times,t));isbeat=sym!='|'
                if isbeat:
                    assert j<len(times) and times[j]==t
                    if j==0 or j==len(times)-1:exclusions[db+':edge']+=1;continue
                    prev,nxt=times[j-1],times[j+1]
                    before=t-prev;after=nxt-t
                    prior=np.diff(times[max(0,j-8):j+1]);previous=prior[-2] if len(prior)>1 else before
                else:
                    if j<len(times) and times[j]==t:exclusions[db+':artifact_coincident_with_beat']+=1;continue
                    if j==0 or j==len(times):exclusions[db+':edge']+=1;continue
                    prev,nxt=times[j-1],times[j]
                    # Candidate-relative distances, never inserted into the true beat stream.
                    before=t-prev;after=nxt-t
                    prior=np.diff(times[max(0,j-9):j]);previous=prior[-1] if len(prior) else before
                reference=float(np.median(prior)) if len(prior) else before
                center=int(np.rint(t*FS));lo=int(np.ceil((prev+t)*FS/2));hi=int(np.ceil((t+nxt)*FS/2))
                pos=center+np.arange(LENGTH)-PRE
                mask=(pos>=lo)&(pos<hi)&(pos>=0)&(pos<len(signal))
                if not mask[PRE]:exclusions[db+':center_outside_quantized_bounds']+=1;continue
                if mask.sum()<16:exclusions[db+':short']+=1;continue
                z=np.zeros(LENGTH,np.float32);segment=signal[pos[mask]]
                if segment.std()<1e-6:exclusions[db+':flat']+=1;continue
                z[mask]=segment-np.median(segment)
                a,b,ref=max(before,.05),max(after,.05),max(reference,.05)
                rr=[np.log(a),np.log(b),min(a/ref,5),min(b/ref,5),np.log(ref),min(a/b,5),np.log((hi-lo)/FS),np.log(max(previous,.05))]
                rows.append({'db':db,'record':rec,'group':group,'split':split,'symbol':sym,'sample':int(original),
                             'fs_original':h.fs,'center':center,'left':lo,'right':hi,'valid_points':int(mask.sum()),'lead':lead})
                xs.append(np.stack([z,mask.astype(np.float32)]));rs.append(rr);ys.append(CLASSES.index(sym))
            checks.append({'db':db,'record':rec,'fs':h.fs,'lead':lead,'waveform_sha256':fingerprint})
        print('prepared',db,len(rows),flush=True)
    x=np.array(xs);r=np.array(rs,dtype=np.float32);y=np.array(ys)
    assert np.isfinite(x).all() and np.isfinite(r).all()
    assert np.all(x[:,0][x[:,1]==0]==0) and np.all(x[:,1,PRE]==1)
    partitions={s:{v['group'] for v in rows if v['split']==s} for s in ['train','val','test','external']}
    for a in partitions:
        for b in partitions:
            if a!=b:assert partitions[a].isdisjoint(partitions[b])
    np.savez(out/'beats.npz',x=x,r=r,y=y,db=np.array([v['db'] for v in rows]),group=np.array([v['group'] for v in rows]),split=np.array([v['split'] for v in rows]))
    with (out/'beats.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    counts={db:{s:{c:sum(v['db']==db and v['split']==s and v['symbol']==c for v in rows) for c in CLASSES}
                for s in ['train','val','test','external']} for db,_,_ in sources}
    save(out/'manifest.json',{'classes':CLASSES,'fs':FS,'length':LENGTH,'center':PRE,'counts':counts,'exclusions':dict(exclusions),
         'records':checks,'sha256':sha(out/'beats.npz'),'code_sha256':sha(Path(__file__)),
         'audit':'group disjointness, finite arrays, zero padding, target anchor, exact full-waveform duplicates checked',
         'limits':'offline future RR and zero-phase filter; midpoint bounds not physiological P/T boundaries; no automatic R detection; no INCART realignment; seven original outputs, S excluded explicitly'})

class Residual(nn.Module):
    def __init__(self,a,b,d):
        super().__init__();self.net=nn.Sequential(nn.Conv1d(a,b,5,padding=2*d,dilation=d),nn.GroupNorm(4,b),nn.ReLU(),nn.Conv1d(b,b,5,padding=2),nn.GroupNorm(4,b))
        self.skip=nn.Conv1d(a,b,1) if a!=b else nn.Identity()
    def forward(self,x):return torch.relu(self.net(x)+self.skip(x))

class Network(nn.Module):
    def __init__(self,kind):
        super().__init__();self.kind=kind
        if kind=='baseline':self.base=BeatModel('se_gru');return
        if kind=='multi':
            self.branches=nn.ModuleList([nn.Conv1d(2,16,k,padding=k//2) for k in [5,15,31]])
            self.body=nn.Sequential(Residual(48,32,1),Residual(32,64,2),Residual(64,128,4))
            self.gate=nn.Sequential(nn.Linear(128,16),nn.ReLU(),nn.Linear(16,128),nn.Sigmoid());channels=128
        else:
            self.templates=nn.Conv1d(1,28,41,padding=20,bias=False);channels=28
        self.rr=nn.Sequential(nn.Linear(8,16),nn.ReLU())
        self.head=nn.Sequential(nn.Linear(channels+16,64),nn.ReLU(),nn.Dropout(.2),nn.Linear(64,7))
    def forward(self,x,r):
        if self.kind=='baseline':return self.base(x,r)
        mask=x[:,1:2]
        if self.kind=='multi':
            z=self.body(torch.cat([torch.relu(b(x)) for b in self.branches],1))
            pooled=(z*mask).sum(-1)/mask.sum(-1).clamp_min(1)
            pooled=pooled*self.gate(pooled)
        else:
            z=torch.relu(self.templates(x[:,:1]))
            pooled=z.masked_fill(mask==0,-1e9).amax(-1)
        return self.head(torch.cat([pooled,self.rr(r)],1))

def metrics(y,p):
    return {'accuracy':float(np.mean(y==p)),'macro_f1':float(f1_score(y,p,labels=range(7),average='macro',zero_division=0)),
            'report':classification_report(y,p,labels=range(7),target_names=CLASSES,output_dict=True,zero_division=0),
            'confusion_matrix':confusion_matrix(y,p,labels=range(7)).tolist()}

def fit(kind,mixed,seed):
    name=kind+('_mixed' if mixed else '_mit')+f'_seed{seed}';out=ROOT/'runs'/name
    if (out/'complete.json').exists():return
    out.mkdir(parents=True,exist_ok=True);torch.set_num_threads(8)
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    d=np.load(ROOT/'data/beats.npz');tr=np.flatnonzero((d['split']=='train') & ((d['db']!='svdb') if mixed else (d['db']=='mit')))
    va=np.flatnonzero((d['split']=='val')&(d['db']=='mit'))
    # Same MIT development patients select every model; other holdouts never enter fitting.
    scale=float(np.sqrt((d['x'][tr,0]**2).sum()/d['x'][tr,1].sum()))
    mean=d['r'][tr].mean(0);std=d['r'][tr].std(0)+1e-6
    device='cuda' if torch.cuda.is_available() else 'cpu'
    def tensors(ix):
        x=d['x'][ix].copy();x[:,0]/=scale
        return [torch.as_tensor(v,device=device) for v in [x,np.clip((d['r'][ix]-mean)/std,-8,8).astype(np.float32),d['y'][ix]]]
    tx,rr,y=tensors(tr);vx,vr,vy=tensors(va)
    m=Network(kind).to(device)
    template_indices=[]
    if kind=='template':
        rng=np.random.default_rng(seed)
        with torch.no_grad():
            for c in range(7):
                candidates=np.flatnonzero(d['y'][tr]==c);gs=np.unique(d['group'][tr][candidates])
                for j in range(4):
                    g=gs[j%len(gs)];i=int(rng.choice(candidates[d['group'][tr][candidates]==g]))
                    t=tx[i,0,PRE-20:PRE+21];t=t-t.mean();t=t/t.norm().clamp_min(1e-6)
                    m.templates.weight[c*4+j,0].copy_(t);template_indices.append(int(tr[i]))
    counts=np.bincount(d['y'][tr],minlength=7);weights=np.clip(np.sqrt(counts.max()/counts),1,12);weights/=weights.mean()
    loss_fn=nn.CrossEntropyLoss(weight=torch.tensor(weights,dtype=torch.float32,device=device))
    opt=torch.optim.AdamW(m.parameters(),lr=.001,weight_decay=.01)
    save(out/'config.json',{'kind':kind,'mixed':mixed,'seed':seed,'scale':scale,'rr_mean':mean.tolist(),'rr_std':std.tolist(),
         'parameters':sum(p.numel() for p in m.parameters()),'template_training_indices':template_indices,'data_sha256':sha(ROOT/'data/beats.npz'),
         'code_sha256':sha(Path(__file__)),'classes':CLASSES,'train_counts':counts.tolist(),'selection':'MIT validation seven-class macro-F1'})
    shutil.copy2(__file__,out/'code_snapshot.py')
    best=-1;wait=0;history=[]
    for epoch in range(1,31):
        start=time.time();m.train();total=0
        for ix in torch.randperm(len(y),device=device).split(256):
            opt.zero_grad(set_to_none=True);loss=loss_fn(m(tx[ix],rr[ix]),y[ix]);loss.backward();nn.utils.clip_grad_norm_(m.parameters(),5);opt.step();total+=float(loss.detach())*len(ix)
        m.eval()
        with torch.no_grad():pred=torch.cat([m(vx[i:i+512],vr[i:i+512]).argmax(1) for i in range(0,len(vy),512)]).cpu().numpy()
        result=metrics(d['y'][va],pred);score=result['macro_f1']
        history.append({'epoch':epoch,'loss':total/len(y),'macro_f1':score,'accuracy':result['accuracy'],'seconds':time.time()-start})
        save(out/'history.json',history);print(name,history[-1],flush=True)
        if score>best:
            best=score;wait=0;torch.save(m.state_dict(),out/'best.pt');save(out/'val_metrics.json',result);np.save(out/'val_predictions.npy',pred)
        else:wait+=1
        if wait>=7:break
    save(out/'complete.json',{'best_macro_f1':best,'epochs':epoch})

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','train']);args=p.parse_args()
    if args.stage=='prepare':prepare();return
    if not (ROOT/'protocol.json').exists():
        save(ROOT/'protocol.json',{'classes':CLASSES,'seed0_grid':['baseline_mit','multi_mit','template_mit','baseline_mixed','multi_mixed','template_mixed'],
             'selection':'MIT val macro-F1 only, repeat baseline_mit and seed0 winner seeds1/2; do not select best seed',
             'epochs':30,'patience':7,'loss':'sqrt inverse frequency weighted CE capped12, same policy for all arms',
             'test':'old MIT test unused; INCART test and entire SVDB untouched until final selection',
             'scope':'seven-class direct comparison; SVDB S never relabeled A; no S training in this version'})
    for mixed in [False,True]:
        for kind in ['baseline','multi','template']:fit(kind,mixed,0)
    candidates={p.parent.name:json.loads(p.read_text())['best_macro_f1'] for p in (ROOT/'runs').glob('*seed0/complete.json')}
    winner=max(candidates,key=candidates.get);save(ROOT/'selection.json',{'winner':winner,'scores':candidates})
    kind,domain,_=winner.split('_')
    for seed in [1,2]:
        fit('baseline',False,seed)
        if (kind,domain)!=('baseline','mit'):fit(kind,domain=='mixed',seed)
    print('TRAINING_COMPLETE',flush=True)

if __name__=='__main__':main()

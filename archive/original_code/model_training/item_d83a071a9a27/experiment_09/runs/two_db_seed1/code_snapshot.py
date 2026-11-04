"""Six-database beat classification; streamed arrays, fixed source/subject groups."""
from pathlib import Path
import sys,json,csv,hashlib,collections,time,math,shutil
import numpy as np
import wfdb
from scipy.signal import resample_poly
import torch
from torch import nn
from sklearn.metrics import classification_report,confusion_matrix,f1_score
from inventory import ROOT,PROJECT,SOURCES
sys.path.insert(0,str(PROJECT/'experiment_08'))
from filtering import filter_ecg
from run import Network

CLASSES=['A','F','L','N','R','S','V','|'];COMMON=[c for c in CLASSES if c!='S']
BEATS=set('NLRaVFJASEj/QBenfr');FS=256;PRE=77;LENGTH=205
DATA=ROOT/'data'

def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def assign(rows):
    previous=json.loads((PROJECT/'experiment_08/data/split.json').read_text())
    incfolder=next(f for db,f,_ in SOURCES if db=='incart');patient=None;inc={}
    for line in (incfolder/'files-patients-diagnoses.txt').read_text().splitlines():
        if line.startswith('patient '):patient=line.strip().replace(' ','_')
        elif line.startswith('I'):
            for record in line.split():inc[record]=patient
    edb_groups=[['e0118','e0119','e0120','e0121','e0122'],['e0123','e0124','e0125','e0126'],
                ['e0129','e0133'],['e0136','e0139'],['e0147','e0148'],['e0154','e0155'],['e0162','e0163']]
    edb={record:group[0] for group in edb_groups for record in group}
    for r in rows:
        db,rec=r['db'],r['record']
        g=('201+202' if rec in ['201','202'] else rec) if db=='mit' else inc[rec] if db=='incart' else edb.get(rec,rec) if db=='edb' else rec
        r['group']=db+':'+g
        if db=='mit':r['split']=previous['mit'].get(rec,'train')
        elif db=='incart':r['split']=previous['incart'][g]
        elif db in ['stdb','svdb']:r['split']='train'  # No certified cross-record identities: keep entire source together.
    for db in ['edb','sddb']:
        groups=sorted({r['group'] for r in rows if r['db']==db})
        np.random.default_rng(2026102409).shuffle(groups);n=max(1,round(.2*len(groups)))
        mapping={g:('test' if i<n else 'val' if i<2*n else 'train') for i,g in enumerate(groups)}
        for r in rows:
            if r['db']==db:r['split']=mapping[r['group']]
    return rows

def prepare():
    assert not (DATA/'manifest.json').exists(),'Frozen dataset exists'
    rows=assign(json.loads((ROOT/'inventory.json').read_text(encoding='utf-8'))['records'])
    save(DATA/'record_plan.json',rows)
    (DATA/'shards').mkdir(exist_ok=True)
    excluded=collections.Counter();records=[];hashes={};offset=0;chunks={};total_counts=collections.Counter()
    for rid,row in enumerate(rows):
        shard=DATA/'shards'/f'{rid:03d}.npz';meta=shard.with_suffix('.json')
        if shard.exists() and meta.exists():
            info=json.loads(meta.read_text(encoding='utf-8'));assert info['record']==row['record'] and info['db']==row['db']
        else:
            base=Path(row['folder'])/row['record'];h=wfdb.rdheader(str(base))
            raw=wfdb.rdrecord(str(base),channels=[h.sig_name.index(row['lead'])]).p_signal[:,0]
            if not np.isfinite(raw).all():
                # Mark gaps, interpolate only for filtering; later exclude every target whose input touches a gap.
                bad=~np.isfinite(raw);good=np.flatnonzero(~bad)
                if len(good)<100:raise RuntimeError('No usable waveform: '+str(base))
                raw[bad]=np.interp(np.flatnonzero(bad),good,raw[good])
            else:bad=None
            digest=hashlib.sha256(raw.tobytes()).hexdigest()
            filtered=filter_ecg(raw,h.fs);signal=resample_poly(filtered,FS,int(h.fs));del filtered
            ann=wfdb.rdann(str(base),'atr');ok=(ann.sample>=0)&(ann.sample<h.sig_len)
            local=collections.Counter({'out_of_bounds':int((~ok).sum())})
            pick=ok&np.array([s in BEATS for s in ann.symbol]);bp=ann.sample[pick]
            # Collapse equal timestamps only in timing stream, not by silently relabeling targets.
            times=np.unique(bp)/h.fs;positions={float(t):i for i,t in enumerate(times)}
            xx=[];rr=[];yy=[];samples=[];counts=collections.Counter()
            seen_targets=set()
            for ai,(p,s) in enumerate(zip(ann.sample,ann.symbol)):
                if not ok[ai]:continue
                if s not in CLASSES:local['outside_targets:'+s]+=1;continue
                if int(p) in seen_targets:local['duplicate_target_timestamp']+=1;continue
                seen_targets.add(int(p));t=p/h.fs;j=int(np.searchsorted(times,t));isbeat=s!='|'
                if isbeat:
                    assert j<len(times) and times[j]==t
                    if j==0 or j==len(times)-1:local['edge']+=1;continue
                    prev,nxt=times[j-1],times[j+1];before=t-prev;after=nxt-t
                    prior=np.diff(times[max(0,j-8):j+1]);last=prior[-2] if len(prior)>1 else before
                else:
                    if j<len(times) and times[j]==t:local['artifact_coincident']+=1;continue
                    if j==0 or j==len(times):local['edge']+=1;continue
                    prev,nxt=times[j-1],times[j];before=t-prev;after=nxt-t
                    prior=np.diff(times[max(0,j-9):j]);last=prior[-1] if len(prior) else before
                center=int(np.rint(t*FS));lo=int(np.ceil((prev+t)*FS/2));hi=int(np.ceil((t+nxt)*FS/2))
                pos=center+np.arange(LENGTH)-PRE;mask=(pos>=lo)&(pos<hi)&(pos>=0)&(pos<len(signal))
                if not mask[PRE] or mask.sum()<16:local['short_or_bad_anchor']+=1;continue
                orig=np.clip(np.rint(pos[mask]*h.fs/FS).astype(int),0,h.sig_len-1)
                if bad is not None and bad[max(0,orig.min()-int(h.fs)):min(h.sig_len,orig.max()+int(h.fs)+1)].any():
                    local['signal_gap_neighborhood']+=1;continue
                z=np.zeros(LENGTH,np.float32);v=signal[pos[mask]];sd=v.std()
                if sd<1e-6:local['flat']+=1;continue
                z[mask]=(v-v.mean())/sd
                a,b,ref=max(before,.05),max(after,.05),max(float(np.median(prior)) if len(prior) else before,.05)
                features=[np.log(a),np.log(b),min(a/ref,5),min(b/ref,5),np.log(ref),min(a/b,5),np.log((hi-lo)/FS),np.log(max(last,.05))]
                xx.append(np.stack([z,mask]));rr.append(features);yy.append(CLASSES.index(s));samples.append(int(p));counts[s]+=1
            x=np.array(xx,dtype=np.float32);r=np.array(rr,dtype=np.float32);y=np.array(yy,dtype=np.int8);samples=np.array(samples,dtype=np.int64)
            assert np.isfinite(x).all() and np.isfinite(r).all() and np.all(x[:,1,PRE]==1)
            assert np.all(x[:,0][x[:,1]==0]==0)
            np.savez(shard,x=x,r=r,y=y,sample=samples)
            info={**row,'counts':dict(counts),'excluded':dict(local),'n':len(y),'waveform_sha256':digest,
                  'source_hashes':{ext:sha(base.with_suffix(ext)) for ext in ['.hea','.atr']},'shard_sha256':sha(shard)}
            save(meta,info);del raw,signal,xx,rr,yy,x,r,y,samples
        digest=info['waveform_sha256']
        if digest in hashes:raise RuntimeError('Duplicate waveform: '+str((row,hashes[digest])))
        hashes[digest]=row['db']+':'+row['record']
        info['id']=rid;info['start']=offset;offset+=info['n'];info['end']=offset;records.append(info)
        excluded.update({row['db']+':'+k:v for k,v in info['excluded'].items()});total_counts.update(info['counts'])
        if rid%10==0:print('prepared',rid+1,'/',len(rows),'samples',offset,flush=True)
    # Pack normalized beats into memory-mapped arrays; never stack millions of Python objects at once.
    specs={'x':((offset,2,LENGTH),np.float32),'r':((offset,8),np.float32),'y':((offset,),np.int8),
           'record':((offset,),np.int16),'split':((offset,),np.int8),'sample':((offset,),np.int64)}
    arrays={k:np.lib.format.open_memmap(DATA/(k+'.npy'),mode='w+',dtype=dtype,shape=shape) for k,(shape,dtype) in specs.items()}
    for info in records:
        sl=slice(info['start'],info['end'])
        with np.load(DATA/'shards'/f"{info['id']:03d}.npz") as chunk:
            for k in ['x','r','y','sample']:arrays[k][sl]=chunk[k]
        arrays['record'][sl]=info['id'];arrays['split'][sl]=['train','val','test'].index(info['split'])
    for a in arrays.values():a.flush()
    groups={s:{r['group'] for r in records if r['split']==s} for s in ['train','val','test']}
    for a in groups:
        for b in groups:
            if a!=b:assert groups[a].isdisjoint(groups[b])
    save(DATA/'manifest.json',{'classes':CLASSES,'records':records,'n':offset,'counts':dict(total_counts),'exclusions':dict(excluded),
          'files':{k:{'sha256':sha(DATA/(k+'.npy')),'shape':list(shape)} for k,(shape,_) in specs.items()},
          'code_sha256':sha(Path(__file__)),'filter_sha256':sha(PROJECT/'experiment_08/filtering.py'),
          'identity_limits':'EDB official same-subject groups; INCART official IDs; MIT201/202 grouped; STDB/SVDB entire source training due unknown identities; cross-database unknown identities remain a limitation',
          'B':'excluded: 54,725/54,727 raw B annotations concentrated in SDDB36; two other single beats do not provide meaningful independent coverage',
          'S':'restored raw S output; never relabeled A','preprocessing':'native-fs 0.5-40Hz + 50Hz Q30 forward/backward; resample256; 205 points anchor77; midpoint mask; valid-point mean/std; physiological RR excludes artifacts'})
    print('DATA_COMPLETE',offset,dict(total_counts),flush=True)

def arrays():return {k:np.load(DATA/(k+'.npy'),mmap_mode='r') for k in ['x','r','y','record','split','sample']}

def model():
    m=Network('multi');m.head[-1]=nn.Linear(64,len(CLASSES));return m

def metric(y,p):
    report=classification_report(y,p,labels=range(8),target_names=CLASSES,output_dict=True,zero_division=0)
    common=y!=CLASSES.index('S')
    if common.any():
        common_report=classification_report(y[common],p[common],labels=range(8),target_names=CLASSES,output_dict=True,zero_division=0)
        common_f1=float(np.mean([common_report[c]['f1-score'] for c in COMMON]))
    else:common_f1=None
    return {'accuracy':float((y==p).mean()),'macro_f1':float(f1_score(y,p,labels=range(8),average='macro',zero_division=0)),
            'common7_accuracy':float((y[common]==p[common]).mean()) if common.any() else None,'common7_macro_f1':common_f1,
            'report':report,'confusion_matrix':confusion_matrix(y,p,labels=range(8)).tolist(),
            'all_normal_accuracy':float((y==CLASSES.index('N')).mean())}

def indices(d,records,arm,split):
    allowed=np.array([r['id'] for r in records if r['db'] in (['mit','incart'] if arm=='two_db' else [x[0] for x in SOURCES])])
    return np.flatnonzero((d['split']==split)&np.isin(d['record'],allowed))

def predict(m,d,ix,mu,sd):
    pred=[];m.eval()
    with torch.no_grad():
        for start in range(0,len(ix),512):
            batch=ix[start:start+512]
            x=torch.tensor(d['x'][batch],device='cuda');r=torch.tensor(np.clip((d['r'][batch]-mu)/sd,-8,8),device='cuda')
            pred.append(m(x,r).argmax(1).cpu().numpy())
    return np.concatenate(pred)

def development_indices(d,records):
    path=DATA/'selection_indices.npy'
    if path.exists():return np.load(path)
    rng=np.random.default_rng(2026102409);selected=[]
    for db,_,_ in SOURCES:
        ids=[r['id'] for r in records if r['db']==db]
        eligible=(d['split']==1)&np.isin(d['record'],ids)
        for c in range(8):
            candidates=np.flatnonzero(eligible&(d['y']==c))
            selected.extend(rng.choice(candidates,min(2000,len(candidates)),replace=False).tolist())
    ix=np.array(sorted(selected),dtype=np.int64)
    assert (d['split'][ix]==1).all()
    np.save(path,ix);return ix

def fit(arm,seed):
    folder=ROOT/'runs'/f'{arm}_seed{seed}'
    if (folder/'complete.json').exists():return
    folder.mkdir(parents=True,exist_ok=True);torch.set_num_threads(8);torch.manual_seed(seed)
    rng=np.random.default_rng(seed);d=arrays();manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'));records=manifest['records']
    tr=indices(d,records,arm,0)
    mit_ids=[r['id'] for r in records if r['db']=='mit']
    mit_va=np.flatnonzero((d['split']==1)&np.isin(d['record'],mit_ids))
    va=development_indices(d,records)
    mu=np.asarray(d['r'][tr]).mean(0);sd=np.asarray(d['r'][tr]).std(0)+1e-6
    counts=np.bincount(d['y'][tr],minlength=8);assert (counts>0).all()
    weights=np.clip(np.sqrt(counts.max()/counts),1,12);weights/=weights.mean()
    m=model().cuda();opt=torch.optim.AdamW(m.parameters(),lr=.001,weight_decay=.01)
    loss_fn=nn.CrossEntropyLoss(weight=torch.tensor(weights,dtype=torch.float32,device='cuda'))
    cfg={'arm':arm,'seed':seed,'classes':CLASSES,'rr_mean':mu.tolist(),'rr_std':sd.tolist(),'train_counts':counts.tolist(),
         'train_n':len(tr),'validation':'fixed multi-source validation subset, at most2000 per source/class; select eight-class macro-F1; report full MIT separately',
         'selection_indices_sha256':sha(DATA/'selection_indices.npy'),
         'round_draws':180000,'max_rounds':24,'patience':6,'batch':256,'minimum_rounds_for_full_coverage':math.ceil(len(tr)/180000),
         'manifest_sha256':sha(DATA/'manifest.json'),'code_sha256':sha(Path(__file__))}
    save(folder/'config.json',cfg);shutil.copy2(__file__,folder/'code_snapshot.py')
    order=rng.permutation(tr);cursor=0;visited=np.zeros(len(d['y']),bool);history=[];best=-1;wait=0
    for epoch in range(1,25):
        start=time.time();draws=[];left=180000
        while left:
            n=min(left,len(order)-cursor);draws.append(order[cursor:cursor+n]);left-=n;cursor+=n
            if cursor==len(order):order=rng.permutation(tr);cursor=0
        draws=np.concatenate(draws);visited[draws]=True;m.train();loss_total=0
        for pos in range(0,len(draws),256):
            batch=draws[pos:pos+256];x=torch.tensor(d['x'][batch],device='cuda')
            r=torch.tensor(np.clip((d['r'][batch]-mu)/sd,-8,8),device='cuda');y=torch.tensor(d['y'][batch].astype(np.int64),device='cuda')
            opt.zero_grad(set_to_none=True);loss=loss_fn(m(x,r),y);loss.backward();nn.utils.clip_grad_norm_(m.parameters(),5);opt.step();loss_total+=loss.item()*len(batch)
        pred=predict(m,d,va,mu,sd);result=metric(d['y'][va],pred);score=result['macro_f1']
        mit_pred=predict(m,d,mit_va,mu,sd);mit_result=metric(d['y'][mit_va],mit_pred)
        history.append({'round':epoch,'loss':loss_total/len(draws),'accuracy':result['accuracy'],'macro_f1':result['macro_f1'],
                        'mit_accuracy':mit_result['common7_accuracy'],'mit_common7_macro_f1':mit_result['common7_macro_f1'],
                        'seconds':time.time()-start,'unique_training_seen':int(visited[tr].sum())})
        save(folder/'history.json',history);print(arm,seed,history[-1],flush=True)
        # A checkpoint is eligible only after its training has seen the entire included dataset.
        eligible=bool(visited[tr].all())
        if eligible and score>best:
            best=score;wait=0;torch.save(m.state_dict(),folder/'best.pt');save(folder/'val_metrics.json',result);np.save(folder/'val_predictions.npy',pred)
            save(folder/'mit_val_metrics.json',mit_result);np.save(folder/'mit_val_predictions.npy',mit_pred)
        elif eligible:wait+=1
        if wait>=6 and eligible:break
    assert visited[tr].all(),'Not every included training sample was visited'
    save(folder/'complete.json',{'best_selection_macro_f1':best,'rounds':epoch,'all_training_samples_seen':True,'unique_seen':int(visited[tr].sum())})

def train():
    save(ROOT/'protocol.json',{'arms':['two_db','six_db'],'seeds':[0,1,2],'selection':'frozen multi-source validation subset max2000/source/class; eight-class macro-F1, same subset for both arms',
         'same_architecture':'multi-scale residual + RR, 8 outputs','round_draws':180000,'sampling':'uniform shuffled full pass with cyclic carry; every training sample visited before stopping',
         'max_rounds':24,'patience':6,'comparison':'same eight outputs, optimizer and number of draws per round; not old seven-output weights',
         'filter':'retain user 50Hz Q30 notch plus bidirectional .5-40Hz bandpass','test':'frozen until training all arms/seeds complete; old test cohorts already used historically, not pristine external evidence'})
    for seed in [0,1,2]:
        for arm in ['two_db','six_db']:fit(arm,seed)
    print('TRAIN_COMPLETE',flush=True)

if __name__=='__main__':
    {'prepare':prepare,'train':train}[sys.argv[1]]()

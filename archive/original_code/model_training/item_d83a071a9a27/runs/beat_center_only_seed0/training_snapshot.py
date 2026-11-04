from pathlib import Path
import argparse,collections,csv,hashlib,json,os,random,time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'项目复现'/'ECG_ren'
ARCHIVE=ROOT/'历史归档_10秒窗口方案_2026-10-24'
DATABASES=[('european-st-t-database-1.0.0','MLIII'),('mit-bih-arrhythmia-database-1.0.0','MLII'),
           ('mit-bih-st-change-database-1.0.0','ECG'),('sudden-cardiac-death-holter-database-1.0.0','ECG')]
CLASSES=['A','B','F','L','N','R','S','V','|']
CANDIDATES=set('NLRaVFJASEj/QBenfr')|{'|'}

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def table(p,rows):
    if not rows:return
    with open(p,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def boundaries(points,length):
    """Cycle borders are midpoints between adjacent annotated candidates, not fixed 10s."""
    points=np.asarray(points,dtype=np.int64)
    left=np.zeros(len(points),dtype=np.int64);right=np.full(len(points),length,dtype=np.int64)
    mids=(points[:-1]+points[1:])//2
    left[1:]=mids;right[:-1]=mids
    return left,right

def rr_features(points,fs,left,right):
    rr=np.diff(points)/fs
    pre=np.r_[rr[0],rr];post=np.r_[rr,rr[-1]]
    padded=np.pad(pre,(7,0),mode='edge')
    local=np.median(np.lib.stride_tricks.sliding_window_view(padded,8),axis=1)
    pre=np.clip(pre,.05,10);post=np.clip(post,.05,10);local=np.clip(local,.05,10)
    duration=np.maximum((right-left)/fs,.001)
    return np.stack([np.log(pre),np.log(post),np.clip(pre/local,0,5),np.clip(post/local,0,5),
      np.clip(pre/post,0,5),np.log(local),(points-left)/np.maximum(right-left,1),np.log(duration)],axis=1).astype('float32')

def prepare():
    import wfdb
    out=ROOT/'data';out.mkdir(exist_ok=True)
    if (out/'manifest.json').exists():raise SystemExit('Beat dataset already frozen')
    # Reuse record membership only; all labels and beats are regenerated from raw annotations.
    with open(ARCHIVE/'data/split_coverage.csv',encoding='utf-8-sig',newline='') as f:
        group_split={r['group']:r['split'] for r in csv.DictReader(f)}
    manifest={'task':'one annotated candidate cycle -> its own raw symbol; center label only',
      'classes':CLASSES,'no_mapping':'A != S; V != F; paced beats are not N',
      'boundaries':'adjacent candidate midpoint borders; 256 interpolated points per cycle',
      'context':'previous, center, next normalized cycles; context has no target labels as inputs',
      'rr':'8 label-free timing features from annotation positions; previous-eight RR median',
      'limitations':['Expert timing is an oracle: detector errors are not assessed.',
        'Right neighbor and post-RR require future beats; this is not zero-lookahead inference.',
        '| denotes artifact candidate, not a physiological heartbeat.',
        'Record split is a patient proxy; cross-record identities not fully certified.'],
      'source':str(SOURCE),'split_source_sha256':sha(ARCHIVE/'data/split_coverage.csv'),
      'prepare_code_sha256':sha(Path(__file__)),'records':[],'excluded':{}}
    excluded=collections.Counter();offset=0;records=[]
    fields=['index','record_id','database','record','group','split','sample','time_sec','left_sample','right_sample','symbol','label','eligible']
    with open(out/'beats.csv','w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for db,lead in DATABASES:
            folder=SOURCE/db
            for rec in (folder/'RECORDS').read_text().splitlines():
                rec=rec.strip();base=folder/rec
                if not rec or not base.with_suffix('.atr').exists():continue
                head=wfdb.rdheader(str(base))
                if lead not in head.sig_name:continue
                group=f'{db}:{"201+202" if db.startswith("mit-bih-arrhythmia") and rec in ("201","202") else rec}'
                if group not in group_split:raise RuntimeError('Unassigned record: '+group)
                signal=wfdb.rdrecord(str(base),channels=[head.sig_name.index(lead)]).p_signal[:,0]
                ann=wfdb.rdann(str(base),'atr');fs=float(head.fs)
                selected=np.array([s in CANDIDATES for s in ann.symbol]);positions=np.asarray(ann.sample)[selected];symbols=np.asarray(ann.symbol)[selected]
                # Duplicate positions cannot define separate non-overlapping cycles. Log and retain first deterministically.
                unique=np.r_[True,np.diff(positions)>0];excluded['duplicate_position']+=int((~unique).sum());positions=positions[unique];symbols=symbols[unique]
                if len(positions)<4:continue
                left,right=boundaries(positions,len(signal));rr=rr_features(positions,fs,left,right)
                wave=np.zeros((len(positions),256),dtype='float32');good=np.ones(len(positions),dtype=bool)
                for i,(lo,hi) in enumerate(zip(left,right)):
                    seg=signal[lo:hi];duration=(hi-lo)/fs
                    if len(seg)<8 or duration<.08 or duration>4 or not np.isfinite(seg).all():
                        good[i]=False;excluded['bad_cycle']+=1;continue
                    v=np.interp(np.linspace(0,len(seg)-1,256),np.arange(len(seg)),seg).astype('float32')
                    v-=v.mean();sd=v.std()
                    if sd<=1e-8:good[i]=False;excluded['constant_cycle']+=1;continue
                    wave[i]=v/(sd+1e-8)
                # No edge padding or context across records. Ineligible cycles may not be used as context.
                eligible=good.copy();eligible[0]=eligible[-1]=False
                eligible[1:-1]&=good[:-2]&good[2:]
                label=np.array([CLASSES.index(s) if s in CLASSES else -1 for s in symbols],dtype='int64')
                eligible&=label>=0
                neighbors=np.stack([np.maximum(np.arange(len(wave))-1,0),np.arange(len(wave)),np.minimum(np.arange(len(wave))+1,len(wave)-1)],axis=1)+offset
                rid=len(records);prefix=f'{rid:03d}'
                np.save(out/f'{prefix}_wave.npy',wave);np.save(out/f'{prefix}_rr.npy',rr)
                np.save(out/f'{prefix}_neighbors.npy',neighbors);np.save(out/f'{prefix}_labels.npy',label);np.save(out/f'{prefix}_eligible.npy',eligible)
                counts=collections.Counter(symbols[eligible].tolist())
                record={'id':rid,'database':db,'record':rec,'group':group,'split':group_split[group],'lead':lead,'fs':fs,
                  'offset':offset,'length':len(wave),'prefix':prefix,'counts':dict(counts),'hashes':{}}
                for ext in ('.hea','.dat','.atr'):record['hashes'][ext]=sha(base.with_suffix(ext))
                for ext in ('wave','rr','neighbors','labels','eligible'):record['hashes'][ext]=sha(out/f'{prefix}_{ext}.npy')
                records.append(record)
                for i in range(len(wave)):
                    writer.writerow(dict(zip(fields,[offset+i,rid,db,rec,group,group_split[group],int(positions[i]),float(positions[i]/fs),int(left[i]),int(right[i]),str(symbols[i]),int(label[i]),int(eligible[i])])))
                offset+=len(wave);print(db,rec,len(wave),'eligible',int(eligible.sum()),flush=True)
    manifest.update(records=records,excluded=dict(excluded),candidates=offset,metadata_sha256=sha(out/'beats.csv'))
    for split in ('train','val','test'):
        c=collections.Counter()
        for r in records:
            if r['split']==split:c.update(r['counts'])
        manifest[split]={'counts':dict(c),'groups_per_class':{s:len({r['group'] for r in records if r['split']==split and r['counts'].get(s,0)}) for s in CLASSES}}
    dump(out/'manifest.json',manifest)

def load_data():
    m=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'));records=m['records']
    values={k:np.concatenate([np.load(ROOT/'data'/f'{r["prefix"]}_{k}.npy') for r in records]) for k in ['wave','rr','neighbors','labels','eligible']}
    values['record']=np.concatenate([np.full(r['length'],r['id'],dtype='int32') for r in records])
    values['split']=np.concatenate([np.full(r['length'],['train','val','test'].index(r['split']),dtype='int8') for r in records])
    return m,values

def train(epochs,tag,seven=False,center_only=False):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    import torch
    import torch.nn.functional as F
    from sklearn.metrics import classification_report,confusion_matrix,f1_score
    from beat_model import BeatContextNet
    torch.set_num_threads(8);torch.manual_seed(0);np.random.seed(0);random.seed(0)
    torch.backends.cudnn.benchmark=False
    out=ROOT/'runs'/tag
    if out.exists():raise SystemExit('Run exists; choose new tag')
    out.mkdir(parents=True)
    m,d=load_data();classes=[c for c in CLASSES if c not in ('S','F')] if seven else CLASSES
    if seven:
        d['eligible']&=np.isin(d['labels'],[CLASSES.index(c) for c in classes])
        lookup=np.full(9,-1,dtype='int64')
        for j,c in enumerate(classes):lookup[CLASSES.index(c)]=j
        d['labels']=np.where(d['labels']>=0,lookup[np.maximum(d['labels'],0)],-1)
    sets={s:np.flatnonzero(d['eligible']&(d['split']==j)) for j,s in enumerate(['train','val','test'])}
    # Limit normal training beats per record. Keep all abnormalities and all validation/test beats.
    rng=np.random.default_rng(0);selected=[];normal=classes.index('N')
    for r in m['records']:
        if r['split']!='train':continue
        ix=sets['train'][d['record'][sets['train']]==r['id']];n=ix[d['labels'][ix]==normal]
        selected.extend(ix[d['labels'][ix]!=normal]);selected.extend(rng.choice(n,min(3000,len(n)),replace=False))
    sets['train']=np.sort(selected).astype('int64');np.savez(out/'sample_indices.npz',**sets)
    # RR standardization learned on selected training targets only.
    mu=d['rr'][sets['train']].mean(0);sd=d['rr'][sets['train']].std(0)+1e-6
    d['rr']=np.clip((d['rr']-mu)/sd,-8,8).astype('float32')
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    xt=torch.from_numpy(d['wave']).to(device);rt=torch.from_numpy(d['rr']).to(device)
    nt=torch.from_numpy(d['neighbors']).to(device);yt=torch.from_numpy(d['labels']).to(device)
    model=BeatContextNet(len(classes),center_only=center_only).to(device);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    # Prespecified clipped inverse-square-root frequency; never use validation/test counts.
    counts=np.bincount(d['labels'][sets['train']],minlength=len(classes));weights=np.sqrt(counts.max()/np.maximum(counts,1));weights=np.clip(weights,1,8)
    weights=weights/weights.mean();wt=torch.tensor(weights,dtype=torch.float32,device=device)
    config={'classes':classes,'center_only':center_only,'seed':0,'epochs':epochs,'batch_size':512,'normal_cap_per_train_record':3000,
      'parameters':sum(p.numel() for p in model.parameters()),'torch':str(torch.__version__),'device':str(device),
      'manifest_sha256':sha(ROOT/'data/manifest.json'),'code_sha256':sha(Path(__file__)),
      'model_sha256':sha(ROOT/'src/beat_model.py'),'rr_mean':mu.tolist(),'rr_std':sd.tolist(),
      'train_counts':counts.tolist(),'class_weights':weights.tolist(),'protocol':'annotation-timed offline candidate classification; record-isolated',
      'selection':'validation macro-F1 over validation-supported classes; patience 8; no test access until final checkpoint selected'}
    dump(out/'config.json',config)
    import shutil
    shutil.copy2(__file__,out/'training_snapshot.py');shutil.copy2(ROOT/'src/beat_model.py',out/'model_snapshot.py')
    def run(s,training=False):
        model.train(training);ix=sets[s].copy()
        if training:rng.shuffle(ix)
        loss_sum=0;preds=[];truth=[];prob=[]
        with torch.set_grad_enabled(training):
            for st in range(0,len(ix),512):
                indices=torch.tensor(ix[st:st+512],device=device);y=yt[indices]
                logits=model(xt[nt[indices]],rt[indices]);loss=F.cross_entropy(logits,y,weight=wt)
                if training:
                    opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);opt.step()
                loss_sum+=loss.item()*len(y)
                if not training:
                    preds.extend(logits.argmax(1).cpu().tolist());truth.extend(y.cpu().tolist());prob.extend(logits.softmax(1)[:,classes.index('A')].cpu().tolist())
        return loss_sum/len(ix),np.asarray(truth),np.asarray(preds),prob
    best=-1;wait=0;history=[]
    for epoch in range(1,epochs+1):
        t=time.time();tl,_,_,_=run('train',True);vl,y,p,_=run('val');supported=np.unique(y)
        score=float(f1_score(y,p,labels=supported,average='macro',zero_division=0))
        history.append({'epoch':epoch,'train_loss':tl,'val_loss':vl,'val_supported_macro_f1':score,'seconds':time.time()-t});table(out/'history.csv',history)
        if score>best:
            best=score;wait=0;torch.save({'model':model.state_dict(),'epoch':epoch,'classes':classes},out/'best.pt')
        else:wait+=1
        print(history[-1],flush=True)
        if wait>=8:break
    ckpt=torch.load(out/'best.pt',map_location=device,weights_only=True);model.load_state_dict(ckpt['model'])
    for s in ('val','test'):
        _,y,p,prob=run(s);report=classification_report(y,p,labels=list(range(len(classes))),target_names=classes,zero_division=0,output_dict=True)
        result={'epoch':ckpt['epoch'],'accuracy':float((y==p).mean()),'supported_classes':[classes[i] for i in np.unique(y)],
          'supported_macro_f1':float(f1_score(y,p,labels=np.unique(y),average='macro',zero_division=0)),
          'report':report,'confusion_matrix':confusion_matrix(y,p,labels=list(range(len(classes)))).tolist()}
        dump(out/f'{s}_metrics.json',result)
        predictions=[{'index':int(i),'record_id':int(d['record'][i]),'true':classes[a],'pred':classes[b],'prob_A':float(pa)} for i,a,b,pa in zip(sets[s],y,p,prob)]
        table(out/f'{s}_predictions.csv',predictions)
    summary(out,m,classes)

def summary(out,m,classes):
    va=json.loads((out/'val_metrics.json').read_text());te=json.loads((out/'test_metrics.json').read_text())
    text=['# 逐心拍模型实验结果','','每条训练标签仅来自中心候选心拍的原始标注，不做窗口投票。相邻心拍只提供上下文。',
      '', '| 集合 | 准确率 | 有支持类别 macro-F1 |','|---|---:|---:|',
      f'| 验证 | {va["accuracy"]:.2%} | {va["supported_macro_f1"]:.4f} |',f'| 测试 | {te["accuracy"]:.2%} | {te["supported_macro_f1"]:.4f} |',
      '', '| 类别 | 测试样本 | 精确率 | 召回率 | F1 |','|---|---:|---:|---:|---:|']
    for c in classes:
        r=te['report'][c];name=c.replace('|','\\|')
        text.append(f'| {name} | {int(r["support"])} | {r["precision"]:.4f} | {r["recall"]:.4f} | {r["f1-score"]:.4f} |' if r['support'] else f'| {name} | 0 | 无法估计 | 无法估计 | 无法估计 |')
    text+=['','B 独立来源不足，缺类指标不能作泛化结论。记录身份仍不是经完全核实的受试者身份。',
      '使用专家标注定位和构造 RR，属于理想定位的离线评估；还需独立验证自动检测和真实采集。',
      '逐心拍指标与历史十秒窗口指标的任务单位不同，不能直接相减宣称提升。']
    (out/'结果报告.md').write_text('\n'.join(text)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','train']);p.add_argument('--epochs',type=int,default=30);p.add_argument('--tag',default='beat_context_seed0');p.add_argument('--seven',action='store_true');p.add_argument('--center-only',action='store_true');a=p.parse_args()
    prepare() if a.stage=='prepare' else train(a.epochs,a.tag,a.seven,a.center_only)

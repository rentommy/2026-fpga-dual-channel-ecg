"""Rebuild provenance, freeze grouped split, train unchanged baseline, audit A errors."""
from pathlib import Path
import argparse, collections, csv, hashlib, json, os, platform, random, time
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / '项目复现' / 'ECG_ren'
CLASSES = ['A', 'B', 'L', 'N', 'R', 'V', '|']
DATABASES = [('european-st-t-database-1.0.0', 'MLIII'),
             ('mit-bih-arrhythmia-database-1.0.0', 'MLII'),
             ('mit-bih-st-change-database-1.0.0', 'ECG'),
             ('sudden-cardiac-death-holter-database-1.0.0', 'ECG')]
MAP = {**{s:s for s in CLASSES}, 'S':'A', 'F':'V'}

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()

def table(path, rows):
    if not rows: return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def choose_label(symbols):
    # Preserve legacy S/F mapping and N-or-paced-only convention, make ties explicit.
    if symbols and all(s in ('N','/') for s in symbols): return 'N'
    mapped = [MAP[s] for s in symbols if s in MAP]
    abnormal = collections.Counter(s for s in mapped if s != 'N')
    if abnormal: return min(abnormal, key=lambda s:(-abnormal[s], CLASSES.index(s)))
    return 'N' if mapped else 'Q'

def prepare():
    import scipy, wfdb
    from scipy.signal import resample
    out=ROOT/'data'; out.mkdir(exist_ok=True)
    if (out/'manifest.json').exists(): raise SystemExit('Dataset already frozen; use a new directory to rebuild.')
    manifest={'schema':1, 'source':str(SOURCE), 'classes':CLASSES, 'mapping':MAP,
      'label_rule':'most frequent mapped non-N; tie by fixed class order; N or paced-only -> N',
      'quality_rule':'exclude nonfinite, constant (std<=1e-8), or Q; no imputation',
      'preprocessing':'10s non-overlap; Fourier resample 3600; round 3 decimals; per-window zscore during training',
      'group_limit':'record-level proxy, not certified patient independence; MIT 201/202 conservatively merged; cross-database patient identity unknown',
      'numpy':np.__version__, 'scipy':scipy.__version__, 'wfdb':wfdb.__version__, 'files':[], 'skipped':[]}
    for f in sorted((SOURCE/'Data').rglob('*.csv')):
        manifest['files'].append({'path':str(f.relative_to(SOURCE)), 'bytes':f.stat().st_size,'sha256':sha(f)})
    rows=[]; arrays=[]; offset=0; raw_hashes=[]; annotations=collections.Counter()
    for db,lead in DATABASES:
        folder=SOURCE/db
        for rec in (folder/'RECORDS').read_text().splitlines():
            rec=rec.strip(); base=folder/rec
            if not rec or not base.with_suffix('.atr').exists(): continue
            head=wfdb.rdheader(str(base))
            if lead not in head.sig_name:
                manifest['skipped'].append({'db':db,'record':rec,'reason':'missing target lead'}); continue
            for ext in ('.hea','.dat','.atr'):
                f=base.with_suffix(ext)
                if f.exists(): raw_hashes.append({'path':str(f.relative_to(SOURCE)), 'sha256':sha(f)})
            ch=head.sig_name.index(lead); signal=wfdb.rdrecord(str(base), channels=[ch]).p_signal[:,0]
            ann=wfdb.rdann(str(base),'atr'); fs=float(head.fs); win=int(fs*10)
            annotations.update(ann.symbol)
            apos=np.asarray(ann.sample); asym=np.asarray(ann.symbol)
            windows=[]
            for k in range(len(signal)//win):
                st=k*win; en=st+win
                lo,hi=np.searchsorted(apos,[st,en]); syms=asym[lo:hi].tolist(); positions=apos[lo:hi]
                label=choose_label(syms); seg=signal[st:en]
                finite=float(np.isfinite(seg).mean())
                wave=np.round(resample(seg,3600),3).astype('float32') if finite==1 else np.zeros(3600,dtype='float32')
                std=float(wave.std()); reason='nonfinite' if finite<1 else ('constant' if std<=1e-8 else ('Q' if label=='Q' else ''))
                counts=collections.Counter(MAP[s] for s in syms if s in MAP)
                apositions=[float((p-st)/fs) for p,s in zip(positions,syms) if MAP.get(s)=='A']
                group=f'{db}:{"201+202" if db.startswith("mit-bih-arrhythmia") and rec in ("201","202") else rec}'
                row={'index':offset+k,'database':db,'record':rec,'group':group,'lead':lead,'fs':fs,'start_sample':st,
                     'start_sec':st/fs,'label':label,'exclude':reason,'finite_ratio':finite,'std':std,
                     'beat_count':sum(counts.values()),'a_count':counts['A'],
                     'a_fraction':counts['A']/max(sum(counts.values()),1),
                     'a_first_sec':min(apositions) if apositions else -1,
                     'a_positions_sec':json.dumps(apositions),
                     'annotation_counts':json.dumps(dict(collections.Counter(syms))),
                     'a_edge':int(any(p<1 or p>=9 for p in apositions)),
                     'mixed_abnormal':int(sum(v>0 for s,v in counts.items() if s!='N')>1)}
                row.update({f'count_{s if s!="|" else "artifact"}':counts[s] for s in CLASSES})
                rows.append(row); windows.append(wave)
            arr=np.asarray(windows,dtype='float32'); name=f'{len(arrays):03d}.npy'; np.save(out/name,arr)
            arrays.append({'file':name,'offset':offset,'length':len(arr)}); offset+=len(arr)
            print(db,rec,'windows',len(arr),'total',offset,flush=True)
    table(out/'windows.csv',rows); dump(out/'shards.json',arrays)
    manifest['raw_files']=raw_hashes; manifest['windows']=len(rows);manifest['raw_annotation_counts']=dict(annotations)
    manifest['labels']=dict(collections.Counter(r['label'] for r in rows if not r['exclude']))
    manifest['excluded']=dict(collections.Counter(r['exclude'] for r in rows if r['exclude']))
    manifest['metadata_sha256']=sha(out/'windows.csv'); dump(out/'manifest.json',manifest)

def metadata():
    with open(ROOT/'data/windows.csv',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def repair_coverage():
    """Label-only coverage repair; preserve initial split as an audit artifact."""
    path=ROOT/'data/split_coverage.csv'
    if path.exists():raise SystemExit('Coverage split already frozen')
    with open(ROOT/'data/split.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    grouped=collections.defaultdict(list)
    for r in rows:grouped[r['group']].append(r)
    labels={g:set(r['label'] for r in rs) for g,rs in grouped.items()}
    current={g:rs[0]['split'] for g,rs in grouped.items()};moves=[]
    def groups_for(c,s):return {g for g in grouped if current[g]==s and c in labels[g]}
    unavailable=[]
    for c in CLASSES:
        if sum(c in v for v in labels.values())<3:
            unavailable.append(c);continue
        for target in ('train','val','test'):
            if groups_for(c,target):continue
            candidates=[g for g in grouped if c in labels[g] and current[g]!=target
                        and all(len(groups_for(other,current[g]))>1 for other in labels[g])]
            if not candidates:raise RuntimeError(f'Cannot repair {c}/{target} without removing another class')
            g=min(candidates,key=lambda g:(len(grouped[g]),g));moves.append({'group':g,'from':current[g],'to':target,'reason':f'coverage of {c}'})
            current[g]=target
    for r in rows:r['split']=current[r['group']]
    table(path,rows)
    stats={s:{'windows':sum(r['split']==s for r in rows),
      'labels':dict(collections.Counter(r['label'] for r in rows if r['split']==s)),
      'groups_per_class':{c:len(groups_for(c,s)) for c in CLASSES}} for s in ('train','val','test')}
    dump(ROOT/'data/coverage_summary.json',{'method':'label-only deterministic coverage repair before training; smallest eligible group',
      'initial_split_sha256':sha(ROOT/'data/split.csv'),'split_sha256':sha(path),'moves':moves,'classes_with_fewer_than_3_groups':unavailable,'splits':stats})
    print(json.dumps(stats,ensure_ascii=False,indent=2))

def split():
    from sklearn.model_selection import StratifiedGroupKFold
    rows=[r for r in metadata() if not r['exclude']]
    y=np.array([CLASSES.index(r['label']) for r in rows]); g=np.array([r['group'] for r in rows])
    # One prespecified seed; never search splits on resulting model performance.
    outer=StratifiedGroupKFold(5,shuffle=True,random_state=20261023)
    tv,te=next(outer.split(np.zeros(len(y)),y,g))
    inner=StratifiedGroupKFold(4,shuffle=True,random_state=20261024)
    tr0,va0=next(inner.split(np.zeros(len(tv)),y[tv],g[tv])); tr=tv[tr0];va=tv[va0]
    sets={'train':tr,'val':va,'test':te}; groups={s:set(g[i]) for s,i in sets.items()}
    assert not(groups['train']&groups['val'] or groups['train']&groups['test'] or groups['val']&groups['test'])
    assignments=[]; stats={}
    for s,ix in sets.items():
        stats[s]={'windows':len(ix),'groups':len(groups[s]),'labels':dict(collections.Counter(CLASSES[v] for v in y[ix])),
          'groups_per_class':{c:len(set(g[ix][y[ix]==j])) for j,c in enumerate(CLASSES)}}
        for i in ix: assignments.append({'index':rows[i]['index'],'split':s,'group':g[i],'label':rows[i]['label']})
    p=ROOT/'data/split.csv'
    if p.exists(): raise SystemExit('Split already frozen')
    table(p,assignments); dump(ROOT/'data/split_summary.json',{'seed':20261023,'method':'nested StratifiedGroupKFold first fold; nominal 60/20/20; record-group proxy',
      'metadata_sha256':sha(ROOT/'data/windows.csv'),'splits':stats,'missing_classes':{s:[c for c in CLASSES if c not in d['labels']] for s,d in stats.items()}})
    print(json.dumps(stats,ensure_ascii=False,indent=2))

def train(epochs,tag,resume=False):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    import torch
    import torch.nn.functional as F
    from sklearn.metrics import classification_report,confusion_matrix
    from baseline_model import SENetLSTM
    out=ROOT/'runs'/tag
    if out.exists() and not resume: raise SystemExit('Run exists; choose new tag')
    out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(8)
    torch.manual_seed(0);np.random.seed(0);random.seed(0)
    torch.backends.cudnn.benchmark=False
    torch.use_deterministic_algorithms(True,warn_only=True)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu');print(device,flush=True)
    meta=metadata(); shards=json.loads((ROOT/'data/shards.json').read_text())
    X=np.concatenate([np.load(ROOT/'data'/s['file']) for s in shards]); X-=X.mean(axis=1,keepdims=True);X/=X.std(axis=1,keepdims=True)+1e-8
    split_path=ROOT/'data/split_coverage.csv'
    with open(split_path,encoding='utf-8-sig',newline='') as f: assignment=list(csv.DictReader(f))
    splitdata={}
    # Keep arrays in CPU RAM; use GPU cache only when capacity permits.
    cache=device.type=='cuda' and X.nbytes < torch.cuda.mem_get_info()[0]*0.60
    for s in ('train','val','test'):
        ix=np.array([int(r['index']) for r in assignment if r['split']==s]);
        splitdata[s]=(torch.from_numpy(X[ix,None,:]).to(device if cache else 'cpu'),torch.tensor([CLASSES.index(meta[i]['label']) for i in ix],device=device if cache else 'cpu'),ix)
    del X
    model=SENetLSTM().to(device); opt=torch.optim.Adam(model.parameters(),lr=.001)
    weight=torch.tensor([2,1,1,.7,1,2,2],device=device)
    config={'epochs':epochs,'seed':0,'n_weight':.7,'batch_size':256,'lr':.001,'patience':10,'device':str(device),'torch':torch.__version__,
      'gpu':torch.cuda.get_device_name(0) if device.type=='cuda' else None,'classes':CLASSES,'split_sha256':sha(split_path),
      'manifest_sha256':sha(ROOT/'data/manifest.json'),'model_sha256':sha(ROOT/'baseline_model.py'),'pipeline_sha256':sha(Path(__file__)),'python':platform.python_version()}
    if resume:
        original=json.loads((out/'config.json').read_text(encoding='utf-8'))
        for key in ('split_sha256','manifest_sha256','model_sha256'):
            if original[key]!=config[key]:raise RuntimeError(f'Resume provenance mismatch: {key}')
        dump(out/f'resume_environment_{int(time.time())}.json',config)
    else:dump(out/'config.json',config)
    def run(s,training=False):
        model.train(training);xt,yt,_=splitdata[s]; order=torch.randperm(len(yt),device=xt.device) if training else torch.arange(len(yt),device=xt.device)
        loss_sum=0; preds=[];probs=[]
        with torch.set_grad_enabled(training):
            for start in range(0,len(yt),256):
                idx=order[start:start+256];x=xt[idx].to(device);y=yt[idx].to(device)
                logits=model(x); loss=(F.cross_entropy(logits,y,reduction='none')*weight[y]).mean()
                if training: opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
                loss_sum+=loss.item()*len(y)
                if not training: preds.extend(logits.argmax(1).cpu().tolist());probs.extend(logits.softmax(1)[:,0].detach().cpu().tolist())
        return loss_sum/len(yt),np.asarray(preds),probs
    best=-1;wait=0;history=[];start_epoch=1
    if resume:
        state=torch.load(out/'latest.pt',map_location=device,weights_only=True)
        model.load_state_dict(state['model']);opt.load_state_dict(state['optimizer'])
        torch.set_rng_state(state['cpu_rng'].cpu())
        if device.type=='cuda' and state['cuda_rng'] is not None:torch.cuda.set_rng_state(state['cuda_rng'].cpu())
        best=state['best'];wait=state['wait'];history=state['history'];start_epoch=state['epoch']+1
    for epoch in range(start_epoch,epochs+1):
        t=time.time();tl,_,_=run('train',True);vl,p,_=run('val'); y=splitdata['val'][1].cpu().numpy()
        report=classification_report(y,p,labels=list(range(7)),target_names=CLASSES,output_dict=True,zero_division=0);f1=report['macro avg']['f1-score']
        history.append({'epoch':epoch,'train_loss':tl,'val_loss':vl,'val_macro_f1':f1,'seconds':time.time()-t});table(out/'history.csv',history)
        if f1>best:
            best=f1;wait=0;torch.save({'model_state_dict':model.state_dict(),'classes':CLASSES,'epoch':epoch,'val_macro_f1':f1},out/'best.pt')
        else:wait+=1
        torch.save({'model':model.state_dict(),'optimizer':opt.state_dict(),'epoch':epoch,'best':best,'wait':wait,
          'history':history,'cpu_rng':torch.get_rng_state(),
          'cuda_rng':torch.cuda.get_rng_state() if device.type=='cuda' else None},out/'latest.pt')
        print(epoch,history[-1],flush=True)
        if (out/'pause_after_epoch').exists():
            print('Saved epoch boundary; paused for runtime migration.',flush=True);return
        if wait>=10:break
    ckpt=torch.load(out/'best.pt',map_location=device,weights_only=True);model.load_state_dict(ckpt['model_state_dict'])
    for s in ('val','test'):
        loss,p,prob=run(s);y=splitdata[s][1].cpu().numpy()
        report=classification_report(y,p,labels=list(range(7)),target_names=CLASSES,output_dict=True,zero_division=0)
        supported=sorted(set(y.tolist()))
        from sklearn.metrics import f1_score
        dump(out/f'{s}_metrics.json',{'best_epoch':ckpt['epoch'],'weighted_loss':loss,'report':report,
          'accuracy':float((y==p).mean()),'supported_classes':[CLASSES[j] for j in supported],
          'supported_macro_f1':float(f1_score(y,p,labels=supported,average='macro',zero_division=0)),
          'confusion_matrix':confusion_matrix(y,p,labels=list(range(7))).tolist(),'classes':CLASSES})
        predictions=[]
        for ix,pred,pa in zip(splitdata[s][2],p,prob): predictions.append({**meta[ix],'prediction':CLASSES[pred],'prob_A':pa,'correct':int(meta[ix]['label']==CLASSES[pred])})
        table(out/f'{s}_predictions.csv',predictions)
    analyze(out)

def analyze(out):
    # Primary diagnostic uses validation only; test remains a final performance audit.
    with open(out/'val_predictions.csv',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    a=[r for r in rows if r['label']=='A'];stats=[]
    def add(name,subset):
        n=len(subset);hit=sum(r['prediction']=='A' for r in subset)
        if n:
            z=1.96;ph=hit/n;den=1+z*z/n;center=(ph+z*z/(2*n))/den
            half=z*((ph*(1-ph)/n+z*z/(4*n*n))**.5)/den;lo,hi=center-half,center+half
        else:lo=hi=None
        stats.append({'stratum':name,'n':n,'detected_A':hit,'recall':hit/n if n else None,
                      'wilson_low':lo,'wilson_high':hi,'missed_as_N':sum(r['prediction']=='N' for r in subset)})
    add('all_A',a);add('single_A',[r for r in a if int(r['a_count'])==1]);add('multiple_A',[r for r in a if int(r['a_count'])>=2])
    for edge in (0,1):add(f'edge_{edge}',[r for r in a if int(r['a_edge'])==edge])
    for group in sorted(set(r['group'] for r in a)):add(group,[r for r in a if r['group']==group])
    table(out/'A_validation_strata.csv',stats);table(out/'A_validation_errors.csv',[r for r in a if r['prediction']!='A'])
    nrows=[r for r in rows if r['label']=='N']
    dump(out/'analysis.json',{'scope':'validation only','strata':stats,
      'normal_windows':len(nrows),'normal_false_A':sum(r['prediction']=='A' for r in nrows),
      'caution':'association does not establish causation; window Wilson intervals ignore within-record correlation and are descriptive only; no performance ceiling claim'})
    plot_errors(out,a)

def plot_errors(out,a):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    candidates=[]
    # Deterministic representative examples, at most one per record and outcome/count stratum.
    seen=set()
    for r in a:
        key=(r['group'],int(r['a_count'])==1,r['prediction']=='A')
        if key not in seen: candidates.append(r);seen.add(key)
    candidates=candidates[:12]
    if not candidates:return
    shards=json.loads((ROOT/'data/shards.json').read_text());cache={}
    fig,axes=plt.subplots(len(candidates),1,figsize=(14,2.1*len(candidates)),squeeze=False)
    for ax,r in zip(axes[:,0],candidates):
        ix=int(r['index']);s=next(s for s in shards if s['offset']<=ix<s['offset']+s['length'])
        if s['file'] not in cache:cache[s['file']]=np.load(ROOT/'data'/s['file'],mmap_mode='r')
        wave=cache[s['file']][ix-s['offset']];ax.plot(np.arange(3600)/360,wave,linewidth=.6)
        for p in json.loads(r['a_positions_sec']):ax.axvline(p,color='red',alpha=.5,linewidth=.7)
        ax.set_title(f"{r['database']} / {r['record']} / {r['start_sec']}s: true A, predicted {r['prediction']}, A beats={r['a_count']}",fontsize=9)
        ax.set_xlim(0,10);ax.set_ylabel('mV');ax.set_xlabel('seconds; red = annotated A/S position')
    fig.tight_layout();fig.savefig(out/'A_validation_examples.png',dpi=130);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','split','coverage','train','analyze']);p.add_argument('--epochs',type=int,default=60);p.add_argument('--tag',default='record_baseline_seed0');p.add_argument('--resume',action='store_true');a=p.parse_args()
    if a.stage=='prepare':prepare()
    elif a.stage=='split':split()
    elif a.stage=='coverage':repair_coverage()
    elif a.stage=='train':train(a.epochs,a.tag,a.resume)
    else:analyze(ROOT/'runs'/a.tag)

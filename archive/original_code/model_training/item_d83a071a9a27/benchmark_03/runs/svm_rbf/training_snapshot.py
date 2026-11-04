"""MIT-BIH MLII benchmark. Train stages do not evaluate the test set."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,os,random,shutil,time
import numpy as np

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
SOURCE=PROJECT.parent/'项目复现/ECG_ren/mit-bih-arrhythmia-database-1.0.0'
CLASSES=['A','B','F','L','N','R','S','V','|']
EVENTS=set('NLRaVFJASEj/QBenfr')|{'|'}
FS=360;PRE=108;LENGTH=288
PLANNED=['physical_cnn','physical_rr','warped_cnn','warped_rr']

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def table(p,rows):
    if not rows:return
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def extract(signal,point,lo,hi):
    """Exactly one candidate per [lo,hi); physical center always index 108."""
    seg=signal[lo:hi];mu=seg.mean();sd=seg.std()
    positions=point+np.arange(LENGTH)-PRE
    mask=(positions>=lo)&(positions<hi)
    physical=np.zeros(LENGTH,dtype='float32')
    physical[mask]=(signal[positions[mask]]-mu)/(sd+1e-8)
    coords=np.r_[np.linspace(lo,point,PRE,endpoint=False),np.linspace(point,hi-1,LENGTH-PRE)]
    warped=((np.interp(coords,np.arange(lo,hi),seg)-mu)/(sd+1e-8)).astype('float32')
    return np.stack([physical,mask.astype('float32')]),np.stack([warped,np.ones(LENGTH,dtype='float32')])

def prepare():
    import wfdb
    from scipy.signal import butter,sosfiltfilt
    from sklearn.model_selection import StratifiedGroupKFold
    out=ROOT/'data';out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise SystemExit('Frozen dataset exists')
    physical=[];warped=[];timing=[];labels=[];metadata=[];records=[];excluded=collections.Counter()
    sos=butter(3,[.5,40],btype='bandpass',fs=FS,output='sos')
    for rec in SOURCE.joinpath('RECORDS').read_text().splitlines():
        base=SOURCE/rec;head=wfdb.rdheader(str(base))
        if 'MLII' not in head.sig_name:excluded['no_MLII']+=1;continue
        if head.fs!=FS:raise RuntimeError('Unexpected sample rate')
        raw=wfdb.rdrecord(str(base),channels=[head.sig_name.index('MLII')]).p_signal[:,0]
        if not np.isfinite(raw).all():excluded['nonfinite_record']+=1;continue
        signal=sosfiltfilt(sos,raw);ann=wfdb.rdann(str(base),'atr')
        pick=np.array([s in EVENTS for s in ann.symbol]);points=np.array(ann.sample)[pick];symbols=np.array(ann.symbol)[pick]
        if not np.all(np.diff(points)>0):raise RuntimeError('Duplicate or unordered candidates')
        rr=np.diff(points)/FS;pre=np.r_[rr[0],rr];post=np.r_[rr,rr[-1]]
        local=np.median(np.lib.stride_tricks.sliding_window_view(np.pad(pre,(7,0),mode='edge'),8),axis=1)
        rid=len(records);group='201+202' if rec in ('201','202') else rec
        records.append({'record':rec,'group':group,'lead':'MLII','hashes':{ext:sha(base.with_suffix(ext)) for ext in ('.hea','.dat','.atr')}})
        for j in range(1,len(points)-1):
            sym=str(symbols[j])
            if sym not in CLASSES:excluded['outside_nine_classes']+=1;continue
            p=int(points[j]);lo=int((points[j-1]+p)//2);hi=int((p+points[j+1])//2)
            if hi-lo<8 or (hi-lo)/FS>4 or signal[lo:hi].std()<=1e-8:excluded['bad_cycle']+=1;continue
            a,b=extract(signal,p,lo,hi)
            before=max(pre[j],.05);after=max(post[j],.05);reference=max(local[j],.05)
            r=[np.log(before),np.log(after),min(before/reference,5),min(after/reference,5),
               np.log(reference),min(before/after,5),np.log((hi-lo)/FS),np.log(max(pre[j-1],.05))]
            idx=len(labels);physical.append(a);warped.append(b);timing.append(r);labels.append(CLASSES.index(sym))
            metadata.append({'index':idx,'record_id':rid,'record':rec,'group':group,'sample':p,'left':lo,'right':hi,'symbol':sym})
        print('prepared',rec,'total',len(labels),flush=True)
    y=np.array(labels,dtype='int64');g=np.array([r['group'] for r in metadata]);dummy=np.zeros(len(y))
    tv,te=next(StratifiedGroupKFold(5,shuffle=True,random_state=20261024).split(dummy,y,g))
    a,b=next(StratifiedGroupKFold(4,shuffle=True,random_state=20261025).split(dummy[tv],y[tv],g[tv]))
    membership={group:s for s,ix in [('train',tv[a]),('val',tv[b]),('test',te)] for group in set(g[ix])}
    glabels={group:set(y[g==group].tolist()) for group in set(g)};moves=[]
    def gs(c,s):return {group for group in membership if membership[group]==s and c in glabels[group]}
    # Insufficient-source raw classes stay in train, explicitly unvalidated. No model scores used.
    rare={c for c in set(y.tolist()) if sum(c in v for v in glabels.values())<3}
    for c in sorted(rare):
        for group in sorted({group for group in membership if c in glabels[group]}):
            if membership[group]!='train':moves.append({'group':group,'from':membership[group],'to':'train','reason':'insufficient groups for '+CLASSES[c]});membership[group]='train'
    for c in sorted(set(y.tolist())-rare):
        for s in ('train','val','test'):
            if gs(c,s):continue
            candidates=[group for group in membership if c in glabels[group] and membership[group]!=s
              and not (glabels[group]&rare) and all(len(gs(other,membership[group]))>1 for other in glabels[group])]
            if not candidates:raise RuntimeError('Cannot provide coverage without leakage')
            group=min(candidates,key=lambda group:(int((g==group).sum()),group))
            moves.append({'group':group,'from':membership[group],'to':s,'reason':'class coverage '+CLASSES[c]});membership[group]=s
    split=np.array([['train','val','test'].index(membership[v]) for v in g],dtype='int8')
    for row,s in zip(metadata,split):row['split']=['train','val','test'][s]
    table(out/'beats.csv',metadata)
    np.savez(out/'beats.npz',physical=np.array(physical,dtype='float32'),warped=np.array(warped,dtype='float32'),
      rr=np.array(timing,dtype='float32'),labels=y,record=np.array([r['record_id'] for r in metadata],dtype='int16'),split=split)
    manifest={'classes':CLASSES,'fs':FS,'length':LENGTH,'target_index':PRE,'filter':'third-order 0.5-40 Hz zero-phase bandpass applied independently per record',
      'physical':'360 Hz time axis -0.3 to +0.5s; midpoint-bounded central candidate; zero padding plus explicit mask; no time compression',
      'warped':'same central cycle normalized onto 108 pre-target and 180 post-target samples, target aligned; explicit all-valid mask',
      'normalization':'raw filtered central cycle mean/std shared by both modes; no padding in statistics',
      'classes_unsupported_or_insufficient':{CLASSES[c]:sum(c in v for v in glabels.values()) for c in range(9) if sum(c in v for v in glabels.values())<3},
      'records':records,'excluded':dict(excluded),'moves':moves,'source_code_sha256':sha(Path(__file__)),'metadata_sha256':sha(out/'beats.csv'),
      'array_sha256':sha(out/'beats.npz'),'split_seed':[20261024,20261025],'split_method':'nested first grouped stratified fold; label-only coverage repair; 201/202 same subject',
      'limitations':['Annotation-timed offline classification; artifact is not a physiological beat.',
        'Dataset used in prior rounds: this is not a pristine external validation set.',
        'Physical and warped inputs differ in support and validity-mask shape as well as temporal scaling; not an isolated QRS-width causal experiment.']}
    for s in ('train','val','test'):
        ix=np.flatnonzero(split==['train','val','test'].index(s))
        manifest[s]={'count':len(ix),'records':sorted({metadata[i]['record'] for i in ix}),
          'counts':{c:int((y[ix]==j).sum()) for j,c in enumerate(CLASSES)},'patient_groups_per_class':{c:len(set(g[ix][y[ix]==j])) for j,c in enumerate(CLASSES)}}
    dump(out/'manifest.json',manifest);shutil.copy2(__file__,out/'prepare_snapshot.py')
    dump(ROOT/'protocol.json',{'planned_seed0_neural':PLANNED,'classical':'linear SVM on physical morphology + RR',
      'epochs':40,'patience':8,'selection':'highest validation-supported macro-F1 among four CNN configurations, seed0; then repeat selected configuration seeds1/2',
      'final_test':'only after all validation experiments complete; SVM and three selected CNN seeds plus their probability-average ensemble',
      'no_test_tuning':True,'supported_labels':[int(v) for v in np.unique(y[split==1])]})

def load():
    a=np.load(ROOT/'data/beats.npz');return {k:a[k] for k in a.files}
def metrics(y,p):
    from sklearn.metrics import classification_report,confusion_matrix,f1_score
    return {'accuracy':float((y==p).mean()),'supported_macro_f1':float(f1_score(y,p,labels=np.unique(y),average='macro',zero_division=0)),
      'supported_classes':[CLASSES[j] for j in np.unique(y)],'report':classification_report(y,p,labels=list(range(9)),target_names=CLASSES,output_dict=True,zero_division=0),
      'confusion_matrix':confusion_matrix(y,p,labels=list(range(9))).tolist()}
def indices(d,s):return np.flatnonzero(d['split']==['train','val','test'].index(s))

def fit(name,seed=0):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    import torch
    import torch.nn.functional as F
    from models import AlignedCNN
    torch.set_num_threads(8);torch.manual_seed(seed);np.random.seed(seed);random.seed(seed);torch.backends.cudnn.benchmark=False
    out=ROOT/'runs'/f'{name}_seed{seed}'
    if out.exists():raise SystemExit('Run exists')
    out.mkdir(parents=True);d=load();tr=indices(d,'train');va=indices(d,'val')
    mean=d['rr'][tr].mean(0);std=d['rr'][tr].std(0)+1e-6;rr=np.clip((d['rr']-mean)/std,-8,8).astype('float32')
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu');mode=name.split('_')[0];use_rr=name.endswith('_rr')
    # Only training and validation arrays reach the training runner.
    tensor={s:(torch.tensor(d[mode][ix],device=device),torch.tensor(rr[ix],device=device),torch.tensor(d['labels'][ix],device=device)) for s,ix in [('train',tr),('val',va)]}
    counts=np.bincount(d['labels'][tr],minlength=9);weights=np.clip(np.sqrt(counts.max()/np.maximum(counts,1)),1,12);weights/=weights.mean()
    wt=torch.tensor(weights,dtype=torch.float32,device=device)
    model=AlignedCNN(use_rr).to(device);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    cfg={'name':name,'seed':seed,'mode':mode,'use_rr':use_rr,'rr_mean':mean.tolist(),'rr_std':std.tolist(),'weights':weights.tolist(),
      'parameters':sum(p.numel() for p in model.parameters()),'torch':str(torch.__version__),'data_sha256':sha(ROOT/'data/beats.npz'),
      'code_sha256':sha(Path(__file__)),'model_sha256':sha(ROOT/'models.py'),'epochs':40,'patience':8,'batch':256,'lr':.001,'weight_decay':.01}
    dump(out/'config.json',cfg);shutil.copy2(__file__,out/'training_snapshot.py');shutil.copy2(ROOT/'models.py',out/'model_snapshot.py')
    def run(s,training=False):
        model.train(training);x,r,y=tensor[s];order=torch.randperm(len(y),device=device) if training else torch.arange(len(y),device=device)
        total=0;pred=[]
        with torch.set_grad_enabled(training):
            for start in range(0,len(y),256):
                ix=order[start:start+256];logits=model(x[ix],r[ix]);loss=F.cross_entropy(logits,y[ix],weight=wt)
                if training:opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);opt.step()
                total+=loss.item()*len(ix)
                if not training:pred.extend(logits.argmax(1).cpu().tolist())
        return total/len(y),np.array(pred)
    best=-1;wait=0;history=[]
    for ep in range(1,41):
        t=time.time();tl,_=run('train',True);vl,p=run('val');score=metrics(d['labels'][va],p)['supported_macro_f1']
        history.append({'epoch':ep,'train_loss':tl,'val_loss':vl,'val_macro_f1':score,'seconds':time.time()-t});table(out/'history.csv',history)
        if score>best:best=score;wait=0;torch.save({'model':model.state_dict(),'epoch':ep},out/'best.pt')
        else:wait+=1
        print(name,seed,history[-1],flush=True)
        if wait>=8:break
    ck=torch.load(out/'best.pt',map_location=device,weights_only=True);model.load_state_dict(ck['model']);_,p=run('val')
    result=metrics(d['labels'][va],p);result['epoch']=ck['epoch'];dump(out/'val_metrics.json',result)
    np.save(out/'val_predictions.npy',p);table(out/'val_errors.csv',[{'index':int(i),'true':CLASSES[a],'pred':CLASSES[b],'record_id':int(d['record'][i])} for i,a,b in zip(va,d['labels'][va],p) if a!=b])

def features(d):
    x=d['physical'][:,0].reshape(-1,72,4).mean(2);mask=d['physical'][:,1].reshape(-1,72,4).mean(2)
    return np.concatenate([x,mask,d['rr']],axis=1)

def svm(rbf=False):
    import joblib
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC,SVC
    from threadpoolctl import threadpool_limits
    out=ROOT/'runs'/('svm_rbf' if rbf else 'svm');out.mkdir(parents=True,exist_ok=False);d=load();x=features(d);tr=indices(d,'train');va=indices(d,'val')
    scaler=StandardScaler().fit(x[tr]);counts=np.bincount(d['labels'][tr],minlength=9);w=np.clip(np.sqrt(counts.max()/np.maximum(counts,1)),1,12);w/=w.mean()
    model=SVC(C=10,gamma='scale',cache_size=512) if rbf else LinearSVC(C=1,max_iter=10000,random_state=0,dual='auto')
    with threadpool_limits(8):model.fit(scaler.transform(x[tr]),d['labels'][tr],sample_weight=w[d['labels'][tr]])
    joblib.dump({'scaler':scaler,'model':model},out/'model.joblib');p=model.predict(scaler.transform(x[va]));dump(out/'val_metrics.json',metrics(d['labels'][va],p))
    dump(out/'config.json',{'C':10 if rbf else 1,'kernel':'rbf' if rbf else 'linear','gamma':'scale' if rbf else None,'features':'72 waveform bins + 72 mask bins + 8 timing features','data_sha256':sha(ROOT/'data/beats.npz'),'method':'fixed-parameter weighted SVM baseline; not an exact paper reproduction','weights':w.tolist(),'fit_status':getattr(model,'fit_status_',None)})
    shutil.copy2(__file__,out/'training_snapshot.py')
    print('SVM validation',metrics(d['labels'][va],p)['supported_macro_f1'],flush=True)

def select():
    scores={n:json.loads((ROOT/'runs'/f'{n}_seed0/val_metrics.json').read_text())['supported_macro_f1'] for n in PLANNED}
    name=max(PLANNED,key=lambda n:scores[n]);dump(ROOT/'selection.json',{'selected_cnn':name,'seed0_validation_scores':scores,'basis':'validation only','selected_before_test':True})
    print(name)

def predict_cnn(d,folder):
    import torch
    from models import AlignedCNN
    c=json.loads((folder/'config.json').read_text());device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    m=AlignedCNN(c['use_rr']).to(device);m.load_state_dict(torch.load(folder/'best.pt',map_location=device,weights_only=True)['model']);m.eval()
    te=indices(d,'test');r=np.clip((d['rr'][te]-np.array(c['rr_mean']))/np.array(c['rr_std']),-8,8).astype('float32');ps=[]
    with torch.no_grad():
        for start in range(0,len(te),256):
            ix=te[start:start+256];logits=m(torch.tensor(d[c['mode']][ix],device=device),torch.tensor(r[start:start+256],device=device));ps.append(logits.softmax(1).cpu().numpy())
    return np.concatenate(ps)

def finalize():
    import joblib
    out=ROOT/'final'
    if out.exists():raise SystemExit('Final test already frozen')
    selection=json.loads((ROOT/'selection.json').read_text());name=selection['selected_cnn']
    for n in PLANNED:assert (ROOT/'runs'/f'{n}_seed0/val_metrics.json').exists()
    for seed in (0,1,2):assert (ROOT/'runs'/f'{name}_seed{seed}/val_metrics.json').exists()
    d=load();te=indices(d,'test');y=d['labels'][te];out.mkdir()
    classical=joblib.load(ROOT/'runs/svm/model.joblib');pred=classical['model'].predict(classical['scaler'].transform(features(d)[te]))
    dump(out/'svm_metrics.json',metrics(y,pred));np.save(out/'svm_predictions.npy',pred)
    classical_rbf=joblib.load(ROOT/'runs/svm_rbf/model.joblib');pred_rbf=classical_rbf['model'].predict(classical_rbf['scaler'].transform(features(d)[te]))
    dump(out/'svm_rbf_metrics.json',metrics(y,pred_rbf));np.save(out/'svm_rbf_predictions.npy',pred_rbf)
    probabilities=[];results=[]
    for seed in (0,1,2):
        prob=predict_cnn(d,ROOT/'runs'/f'{name}_seed{seed}');p=prob.argmax(1);r=metrics(y,p);dump(out/f'cnn_seed{seed}_metrics.json',r);results.append(r['supported_macro_f1']);probabilities.append(prob)
    prob=np.mean(probabilities,axis=0);p=prob.argmax(1);result=metrics(y,p);dump(out/'ensemble_metrics.json',result)
    table(out/'test_predictions.csv',[{'index':int(i),'record_id':int(d['record'][i]),'true':CLASSES[a],'pred':CLASSES[b],'prob_A':float(pa)} for i,a,b,pa in zip(te,y,p,prob[:,0])])
    group_results=[]
    for rid in np.unique(d['record'][te]):
        keep=d['record'][te]==rid;group_results.append({'record_id':int(rid),'n':int(keep.sum()),'accuracy':float((y[keep]==p[keep]).mean())})
    table(out/'per_record.csv',group_results)
    dump(out/'summary.json',{'selected_cnn':name,'seed_macro_f1':results,'seed_mean':float(np.mean(results)),'seed_std':float(np.std(results)),
      'ensemble_macro_f1':result['supported_macro_f1'],'majority_N_accuracy':float((y==CLASSES.index('N')).mean()),'evaluated_once_after_validation':True})
    report()

def report():
    manifest=json.loads((ROOT/'data/manifest.json').read_text());selection=json.loads((ROOT/'selection.json').read_text());summary=json.loads((ROOT/'final/summary.json').read_text());final=json.loads((ROOT/'final/ensemble_metrics.json').read_text());sv=json.loads((ROOT/'final/svm_metrics.json').read_text());rbf=json.loads((ROOT/'final/svm_rbf_metrics.json').read_text())
    lines=['# MIT-BIH 同导联逐拍基准结果','','本轮只使用 MLII，保留九类原始标签；B 无样本，S 仅两拍且来源不足，无法独立验证九类。',
      '', '| 预处理与模型 | 验证 macro-F1 |','|---|---:|']
    for name,score in selection['seed0_validation_scores'].items():lines.append(f'| {name} | {score:.4f} |')
    v=json.loads((ROOT/'runs/svm/val_metrics.json').read_text());lines.append(f'| 线性 SVM：形态＋RR | {v["supported_macro_f1"]:.4f} |')
    v=json.loads((ROOT/'runs/svm_rbf/val_metrics.json').read_text());lines.append(f'| RBF-SVM：形态＋RR | {v["supported_macro_f1"]:.4f} |')
    lines+=['',f'仅依据验证集选中的神经配置：{summary["selected_cnn"]}。三个种子的测试 macro-F1：{summary["seed_macro_f1"]}，均值 {summary["seed_mean"]:.4f}，标准差 {summary["seed_std"]:.4f}。',
      '', '| 最终模型 | 测试准确率 | 有支持类别 macro-F1 |','|---|---:|---:|',f'| 线性 SVM | {sv["accuracy"]:.2%} | {sv["supported_macro_f1"]:.4f} |',f'| RBF-SVM | {rbf["accuracy"]:.2%} | {rbf["supported_macro_f1"]:.4f} |',f'| 三种子神经模型概率平均 | {final["accuracy"]:.2%} | {final["supported_macro_f1"]:.4f} |',
      '', '| 类别 | 测试拍数 | 独立来源组数 | 精确率 | 召回率 | F1 |','|---|---:|---:|---:|---:|---:|']
    for c in CLASSES:
        r=final['report'][c];label=c.replace('|','\\|');n=manifest['test']['patient_groups_per_class'][c]
        lines.append(f'| {label} | {int(r["support"])} | {n} | {r["precision"]:.4f} | {r["recall"]:.4f} | {r["f1-score"]:.4f} |' if r['support'] else f'| {label} | 0 | 0 | 无法估计 | 无法估计 | 无法估计 |')
    lines+=['',f'全猜 N 的准确率参考：{summary["majority_N_accuracy"]:.2%}。不能只看准确率。',
      '', '## 结论的范围','', '这是同导联、专家候选定位、离线零相位滤波条件下的研究基准，不包含自动检测与硬件误差。',
      '本数据库曾用于前几轮实验，本轮测试未用于配置选择，但不是从未接触过的外部验证。',
      '物理时宽与缩放输入还存在有效范围和 mask 形状差异，结果不能单独证明 QRS 时宽是唯一因果。',
      '三种子只衡量训练随机性，不能代替多个受试者划分或外部数据库验证。B/S 数据覆盖仍需补充。',
      '本轮没有把九类偷偷合并成粗分类，也不把缺少样本的类别计作通过。',
      '', '数据、记录划分、预处理参数、原始文件校验值、源码快照、配置、逐拍预测和各记录成绩均已保存。']
    (ROOT/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','train','svm','svm-rbf','select','finalize','report']);p.add_argument('--name',choices=PLANNED,default='physical_cnn');p.add_argument('--seed',type=int,default=0);a=p.parse_args()
    if a.stage=='prepare':prepare()
    elif a.stage=='train':fit(a.name,a.seed)
    elif a.stage=='svm':svm()
    elif a.stage=='svm-rbf':svm(True)
    elif a.stage=='select':select()
    elif a.stage=='finalize':finalize()
    else:report()

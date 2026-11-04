"""Offline inference on two saved hardware recordings; no training or labels."""
from pathlib import Path
import sys,json,csv,hashlib,math
import numpy as np
from scipy.signal import resample_poly
import torch
import wfdb.processing as wp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
SOURCE=PROJECT.parent/'采集/2026-11-04_真实心电_已保存记录'
INPUT=SOURCE/'02_有效通道完整记录'
sys.path.insert(0,str(PROJECT/'experiment_09'))
from pipeline import model,CLASSES,FS,PRE,LENGTH,filter_ecg

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def write_csv(p,rows):
    if not rows:return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def extract(signal,times):
    xx=[];rr=[];meta=[]
    for j in range(1,len(times)-1):
        prev,t,nxt=times[j-1:j+2];before=t-prev;after=nxt-t
        prior=np.diff(times[max(0,j-8):j+1]);last=prior[-2] if len(prior)>1 else before
        center=int(np.rint(t*FS));lo=int(np.ceil((prev+t)*FS/2));hi=int(np.ceil((t+nxt)*FS/2))
        pos=center+np.arange(LENGTH)-PRE
        mask=(pos>=lo)&(pos<hi)&(pos>=0)&(pos<len(signal))
        if not mask[PRE] or mask.sum()<16:continue
        z=np.zeros(LENGTH,np.float32);v=signal[pos[mask]];sd=v.std()
        if sd<1e-6:continue
        z[mask]=(v-v.mean())/sd
        a,b,ref=max(before,.05),max(after,.05),max(float(np.median(prior)),.05)
        features=[np.log(a),np.log(b),min(a/ref,5),min(b/ref,5),np.log(ref),min(a/b,5),np.log((hi-lo)/FS),np.log(max(last,.05))]
        xx.append(np.stack([z,mask]));rr.append(features)
        meta.append({'detector_index':j,'time_s':float(t),'rr_before_s':float(before),'rr_after_s':float(after),'valid_points':int(mask.sum())})
    x=np.asarray(xx,dtype=np.float32);r=np.asarray(rr,dtype=np.float32)
    assert len(x)>0 and np.isfinite(x).all() and np.isfinite(r).all()
    assert (x[:,1,PRE]==1).all() and (x[:,0][x[:,1]==0]==0).all()
    return x,r,meta

def main():
    torch.set_num_threads(4)
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    candidates=[]
    for folder in sorted((PROJECT/'experiment_09/runs').glob('six_db_seed*')):
        cfg=json.loads((folder/'config.json').read_text(encoding='utf-8'))
        val=json.loads((folder/'val_metrics.json').read_text(encoding='utf-8'))
        assert cfg['classes']==CLASSES and (folder/'complete.json').exists()
        candidates.append((val['macro_f1'],folder,cfg))
    candidates.sort(key=lambda v:(-v[0],str(v[1])))
    primary=candidates[0][1].name
    models=[];model_info=[]
    for score,folder,cfg in candidates:
        m=model().cpu().eval()
        m.load_state_dict(torch.load(folder/'best.pt',map_location='cpu',weights_only=True))
        models.append((m,np.asarray(cfg['rr_mean'],np.float32),np.asarray(cfg['rr_std'],np.float32)))
        model_info.append({'run':folder.name,'selection_macro_f1':score,'weight_path':str(folder/'best.pt'),'weight_sha256':sha(folder/'best.pt'),'config_sha256':sha(folder/'config.json')})
    quality=json.loads((SOURCE/'04_波形与质量/质量与溯源.json').read_text(encoding='utf-8'))
    results=[]
    for path in sorted(INPUT.glob('*.npz')):
        with np.load(path,allow_pickle=False) as z:
            raw_codes=z['raw_codes'];raw=raw_codes.astype(np.float64)*float(z['mV_per_code'])
            fs=int(z['fs_hz']);channel=int(z['channel'])
            assert np.array_equal(z['sample_index'],np.arange(len(raw)))
        assert np.isfinite(raw).all() and fs==500
        duration=len(raw)/fs
        filtered=filter_ecg(raw,fs)
        signal=resample_poly(filtered,FS//math.gcd(fs,FS),fs//math.gcd(fs,FS))
        peaks=wp.xqrs_detect(filtered,fs,verbose=False)
        secondary=wp.gqrs_detect(sig=filtered,fs=fs)
        assert np.all(np.diff(peaks)>0)
        times=peaks/fs
        x,r,meta=extract(signal,times)
        probs=[]
        with torch.inference_mode():
            for m,mu,sd in models:
                rr=np.clip((r-mu)/sd,-8,8)
                probs.append(m(torch.from_numpy(x),torch.from_numpy(rr)).softmax(1).numpy())
        probs=np.asarray(probs);preds=probs.argmax(-1)
        segment=next(s['preferred_segment'] for s in quality['sessions'] if s['recording']==path.stem)
        start=segment['start_nominal_s'];stop=start+segment['duration_nominal_s']
        rows=[]
        for i,info in enumerate(meta):
            t=info['time_s'];rank=np.argsort(probs[0,i])[::-1]
            flags=[]
            if t<2:flags.append('启动前2秒')
            if t>=duration-.5:flags.append('末尾0.5秒')
            match=bool(len(secondary) and np.min(np.abs(secondary/fs-t))<=.100)
            if not match:flags.append('定位器不一致')
            if len(set(preds[:,i]))>1:flags.append('种子预测不一致')
            if probs[0,i].max()<.8:flags.append('模型分数小于0.8')
            row={'beat_number':i+1,**info,'source_sample':int(peaks[info['detector_index']]),'predicted_label':CLASSES[preds[0,i]],
                 'model_score':float(probs[0,i].max()),'second_label':CLASSES[rank[1]],'second_score':float(probs[0,i,rank[1]]),
                 'secondary_detector_match_100ms':match,'three_seed_agreement':bool(np.all(preds[:,i]==preds[0,i])),
                 'outside_start_end_zone':bool(t>=2 and t<duration-.5),'in_saved_preferred_10s':bool(start<=t<stop),'review_flags':';'.join(flags)}
            row.update({f'p_{c if c!="|" else "artifact"}':float(probs[0,i,j]) for j,c in enumerate(CLASSES)})
            row.update({candidates[j][1].name:CLASSES[preds[j,i]] for j in range(len(models))})
            rows.append(row)
        out=ROOT/path.stem;out.mkdir(exist_ok=True)
        write_csv(out/'逐拍预测.csv',rows)
        write_csv(out/'自动定位全部候选.csv',[{'sample':int(p),'time_s':float(p/fs),'used_as_classification_target':bool(j not in [0,len(peaks)-1])} for j,p in enumerate(peaks)])
        np.savez(out/'推理输入与概率.npz',x=x,rr_raw=r,probabilities=probs,detected_samples=peaks,gqrs_samples=secondary,filtered_256hz=signal)
        def count(sub):return {c:sum(v['predicted_label']==c for v in sub) for c in CLASSES}
        valid=[v for v in rows if v['outside_start_end_zone']]
        preferred=[v for v in rows if v['in_saved_preferred_10s']]
        result={'recording':path.stem,'input':str(path),'input_sha256':sha(path),'channel':channel,'fs_hz':fs,'samples':len(raw),'nominal_duration_s':duration,
                'automatic_qrs_count':len(peaks),'secondary_qrs_count':len(secondary),'classified_targets':len(rows),'excluded_first_last_detected_beats':2,
                'counts_all_classified':count(rows),'counts_outside_start_end_zone':count(valid),'n_outside_start_end_zone':len(valid),
                'preferred_10s':[start,stop],'counts_preferred_10s':count(preferred),'n_preferred_10s':len(preferred),
                'median_rr_bpm':float(60/np.median(np.diff(times))),'rr_min_s':float(np.diff(times).min()),'rr_max_s':float(np.diff(times).max()),
                'primary_mean_model_score':float(probs[0].max(-1).mean()),'three_seed_disagreement_count':sum(not v['three_seed_agreement'] for v in rows),
                'secondary_detector_unmatched_targets':sum(not v['secondary_detector_match_100ms'] for v in rows),
                'adc_clipped_samples':int(np.sum((raw_codes<=-8388608)|(raw_codes>=8388607)))}
        save(out/'summary.json',result);results.append(result)
        fig,axs=plt.subplots(4,1,figsize=(16,10),layout='constrained')
        for a in range(3):
            ax=axs[a];left=a*8;right=min((a+1)*8,duration);ix=(np.arange(len(filtered))/fs>=left)&(np.arange(len(filtered))/fs<right)
            ax.plot(np.arange(len(filtered))[ix]/fs,filtered[ix],lw=.7,color='#34546e')
            ax.axvspan(max(left,0),min(right,2),alpha=.12,color='gray') if left<2 else None
            for v in rows:
                t=v['time_s']
                if left<=t<right:
                    color='#168351' if v['predicted_label']=='N' else '#c73b39'
                    ax.scatter(t,filtered[v['source_sample']],s=20,c=color)
                    ax.annotate(f"{v['beat_number']}:{v['predicted_label']}",(t,filtered[v['source_sample']]),xytext=(0,14),textcoords='offset points',ha='center',fontsize=8,color=color)
            ax.set_xlim(left,right);ax.set_ylabel('滤波后 mV');ax.grid(alpha=.15)
        ax=axs[3]
        for c in np.unique(preds[0]):
            ix=np.flatnonzero(preds[0]==c);ax.scatter([meta[i]['time_s'] for i in ix],probs[0,ix,c],label=CLASSES[c],s=28)
        ax.set_ylim(0,1.04);ax.set_xlim(0,duration);ax.set_xlabel('标称时间 / 秒');ax.set_ylabel('模型类别分数');ax.legend()
        fig.suptitle(f'{path.stem} | {primary} | 自动定位＋逐拍预测（无人工真值）')
        fig.savefig(out/'完整记录预测.png',dpi=160);plt.close(fig)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    report={'date':'2026-11-04','selection_rule':'latest completed six-database arm, highest saved development selection macro-F1; no selection on capture predictions or test scores',
            'primary_run':primary,'classes':CLASSES,'models':model_info,'records':results,
            'preprocessing':'raw ADC -> nominal mV -> native 500Hz 0.5-40Hz order3 sosfiltfilt -> 50Hz Q30 notch sosfiltfilt -> resample_poly256 -> 205pt center77 midpoint mask -> valid mean/std; 8 RR features normalized with saved training mean/std clipped±8',
            'detection':'WFDB XQRS on filtered500Hz; GQRS independent timing check±100ms; first/last detected peaks omitted as targets but retained as timing context',
            'limits':['no expert beat labels, so no accuracy/precision/recall can be computed','model scores are uncalibrated softmax, not diagnostic confidence','automatic detections may include artifacts and alter RR; training used reference annotations','first2s and final0.5s flagged, not silently deleted','new hardware electrode configuration is not certified identical to training MLII/MLIII','two separate recordings of one person; not stitched together','S is original raw S; | is artifact, not a true beat type'],
            'script_sha256':sha(Path(__file__))}
    save(ROOT/'summary.json',report)
    print('INFERENCE_COMPLETE',primary,flush=True)

if __name__=='__main__':main()

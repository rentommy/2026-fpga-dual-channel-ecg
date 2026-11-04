"""Deterministic original-waveform review of previous validation errors."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mplcache'))
import csv,json
import numpy as np
import wfdb
from scipy.signal import butter,sosfiltfilt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from study import CLASSES,OLD,save,table

def main():
    out=ROOT/'waveform_review';out.mkdir(exist_ok=False)
    data=ROOT.parent/'benchmark_03/data';d=np.load(data/'beats.npz');meta=list(csv.DictReader((data/'beats.csv').open(encoding='utf-8-sig')))
    lookup=np.array([CLASSES.index(c) if c in CLASSES else -1 for c in OLD]);y=lookup[d['labels']]
    va=np.flatnonzero((d['split']==1)&(y>=0));pred=np.load(ROOT.parent/'reference_04/runs/se_gru/val_predictions.npy');assert len(va)==len(pred)
    source=ROOT.parent.parent/'项目复现/ECG_ren/mit-bih-arrhythmia-database-1.0.0'
    cached={};audit=[];review=[]
    def original(i):
        row=meta[i];rec=row['record']
        if rec not in cached:
            h=wfdb.rdheader(str(source/rec));raw=wfdb.rdrecord(str(source/rec),channels=[h.sig_name.index('MLII')]).p_signal[:,0]
            filtered=sosfiltfilt(butter(3,[.5,40],btype='bandpass',fs=360,output='sos'),raw)
            ann=wfdb.rdann(str(source/rec),'atr');cached[rec]=(raw,filtered,dict(zip(ann.sample,ann.symbol)))
        raw,filtered,ann=cached[rec];p=int(row['sample']);lo=int(row['left']);hi=int(row['right'])
        assert ann[p]==row['symbol'];positions=p+np.arange(288)-108;mask=(positions>=lo)&(positions<hi)
        seg=filtered[lo:hi];reconstructed=np.zeros(288);reconstructed[mask]=(filtered[positions[mask]]-seg.mean())/(seg.std()+1e-8)
        np.testing.assert_allclose(reconstructed,d['physical'][i,0],atol=2e-6,rtol=2e-6)
        audit.append({'index':int(i),'record':rec,'original_label_matches':True,'filtered_waveform_matches':True})
        return raw,p,lo,hi
    records=np.array([meta[i]['record'] for i in va])
    for label in ['A','L','R']:
        c=CLASSES.index(label);train=np.flatnonzero((d['split']==0)&(y==c));train_ref=int(train[0])
        for rec in np.unique(records[y[va]==c]):
            keep=(records==rec)&(y[va]==c);wrong=keep&(pred!=c);correct=keep&(pred==c);counts=np.bincount(pred[keep],minlength=7)
            review.append({'class':label,'record':rec,'support':int(keep.sum()),'correct':int(correct.sum()),'recall':float(correct.sum()/keep.sum()),'dominant_prediction':CLASSES[counts.argmax()]})
            selected=[(train_ref,'training reference (first available)')]
            if correct.any():j=np.flatnonzero(correct)[0];selected.append((int(va[j]),'validation correct'))
            if wrong.any():j=np.flatnonzero(wrong)[0];selected.append((int(va[j]),'validation error -> '+CLASSES[pred[j]]))
            fig,axes=plt.subplots(len(selected),3,figsize=(14,3*len(selected)),squeeze=False)
            for k,(i,status) in enumerate(selected):
                raw,p,lo,hi=original(i);row=meta[i];left=max(0,p-180);right=min(len(raw),p+216);t=(np.arange(left,right)-p)/360*1000
                axes[k,0].plot(t,raw[left:right],lw=1);axes[k,0].axvspan((lo-p)/360*1000,(hi-p)/360*1000,color='green',alpha=.12)
                axes[k,0].set_title(f'{status}; {row["record"]}:{p}; true {label}');axes[k,0].set_xlabel('Raw MLII, relative time (ms)')
                axes[k,1].plot((np.arange(288)-108)/360*1000,d['physical'][i,0],lw=1);axes[k,1].set_title('Filtered, normalized, original time');axes[k,1].set_xlabel('Time (ms)')
                axes[k,2].plot(np.arange(288)-108,d['warped'][i,0],lw=1);axes[k,2].set_title(f'Network input; pre/post RR {np.exp(d["rr"][i,0]):.3f}/{np.exp(d["rr"][i,1]):.3f}s');axes[k,2].set_xlabel('Normalized sample index')
                for ax in axes[k]:ax.axvline(0,color='red',alpha=.5);ax.grid(alpha=.2)
            fig.tight_layout();fig.savefig(out/f'{label}_{rec}.png',dpi=130);plt.close(fig)
    table(out/'per_record_errors.csv',review);save(out/'source_checks.json',{'passed':True,'checks':audit,'selection':'first training reference and first correct/incorrect validation beat per class-record; not representative prevalence estimates'})
    lines=['# 波形和错误审核','','按 A/L/R 的每条验证记录生成原始波形、固定时宽处理结果、网络实际输入三列对照。每张图固定选第一个训练参考及该记录第一个正确/错误目标，不按外观挑图。',
      '所有选中样本均重新核对原始标注并重建滤波与归一化输入，数值一致。此前完整数据核查也通过；这些检查能排除所查样本的标签索引和数组构造错误，不能证明切分/滤波在生理信息上最优。',
      '', '| 类别 | 验证记录 | 拍数 | 正确数 | 召回率 | 最常预测为 |','|---|---|---:|---:|---:|---|']
    for r in review:lines.append(f'| {r["class"]} | {r["record"]} | {r["support"]} | {r["correct"]} | {r["recall"]:.2%} | {r["dominant_prediction"]} |')
    lines+=['','图中红线为专家标注位置，不保证是 R 波正峰。固定窗与周期边界可能丢失远离中心的波形，周期缩放会改变相对时宽；本轮不据个别图随意删除困难记录。',
      '未引入自动 P/QRS/T 起止检测；后续显式特征只称为局部形态描述，不能当作临床 QRS 时长。']
    (out/'审核说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Waveform source checks passed; plots saved.',flush=True)
if __name__=='__main__':main()

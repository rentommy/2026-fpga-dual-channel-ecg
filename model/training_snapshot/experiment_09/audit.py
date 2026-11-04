import json
import numpy as np
import wfdb
from pathlib import Path
from pipeline import ROOT,DATA,CLASSES,BEATS,PRE,arrays,sha,save

def main():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'));d=arrays()
    for k,info in manifest['files'].items():assert sha(DATA/(k+'.npy'))==info['sha256'],k
    groups={s:{r['group'] for r in manifest['records'] if r['split']==s} for s in ['train','val','test']}
    for a in groups:
        for b in groups:
            if a!=b:assert groups[a].isdisjoint(groups[b])
    verified=0;true_rr=0;normalization_max_error=0.
    for row in manifest['records']:
        sl=slice(row['start'],row['end']);base=Path(row['folder'])/row['record'];ann=wfdb.rdann(str(base),'atr');fs=row['fs']
        lookup=set(zip(ann.sample.tolist(),ann.symbol))
        ps=d['sample'][sl];labels=d['y'][sl]
        assert all((int(p),CLASSES[int(c)]) in lookup for p,c in zip(ps,labels))
        times=np.unique([p/fs for p,s in zip(ann.sample,ann.symbol) if s in BEATS and 0<=p<row['samples']])
        keep=labels!=CLASSES.index('|');t=ps[keep]/fs;j=np.searchsorted(times,t)
        assert np.all(times[j]==t)
        expected=np.log(np.stack([np.maximum(t-times[j-1],.05),np.maximum(times[j+1]-t,.05)],1))
        np.testing.assert_allclose(d['r'][sl][keep,:2],expected,atol=1e-6)
        x=d['x'][sl];assert np.isfinite(x).all() and np.isfinite(d['r'][sl]).all()
        mask=x[:,1];assert np.all(mask[:,PRE]==1) and np.all(x[:,0][mask==0]==0)
        n=mask.sum(1);mu=x[:,0].sum(1)/n;sd=np.sqrt((x[:,0]**2).sum(1)/n)
        error=max(float(np.abs(mu).max()),float(np.abs(sd-1).max()))
        assert error<1e-5;normalization_max_error=max(normalization_max_error,error)
        verified+=row['n'];true_rr+=int(keep.sum())
    save(ROOT/'audit.json',{'passed':True,'labels_and_positions_verified':verified,'physiological_pre_post_rr_verified':true_rr,
         'group_disjointness':True,'normalization_max_error':normalization_max_error,
         'source_identity_limits':manifest['identity_limits'],'scope':'no exact full-waveform duplicate; partial overlap and undisclosed cross-database identities not certified'})
    print('AUDIT_PASS',verified,true_rr,flush=True)

if __name__=='__main__':main()

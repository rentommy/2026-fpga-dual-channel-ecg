"""Check saved preprocessing against original annotations independently."""
import csv,json
import numpy as np
import wfdb
from run import ROOT,PROJECT,BEATS,PRE,FS,CLASSES,sha,save

with np.load(ROOT/'data/beats.npz') as archive:
    d={key:archive[key] for key in archive.files}
rows=list(csv.DictReader((ROOT/'data/beats.csv').open(encoding='utf-8-sig')))
m=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
assert sha(ROOT/'data/beats.npz')==m['sha256']
assert len(rows)==len(d['y'])
assert np.isfinite(d['x']).all() and np.isfinite(d['r']).all()
assert np.all(d['x'][:,1,PRE]==1)
assert np.all(d['x'][:,0][d['x'][:,1]==0]==0)
groups={s:set(d['group'][d['split']==s]) for s in np.unique(d['split'])}
for a in groups:
    for b in groups:
        if a!=b:assert groups[a].isdisjoint(groups[b])
sources={'mit':PROJECT.parent/'项目复现/ECG_ren/mit-bih-arrhythmia-database-1.0.0',
         'incart':PROJECT.parent/'样本/incartdb-1.0.0','svdb':PROJECT.parent/'样本/svdb-1.0.0'}
# Every retained target is checked against the original symbol and sample.
cache={};verified=0
for i,row in enumerate(rows):
    key=(row['db'],row['record'])
    if key not in cache:
        ann=wfdb.rdann(str(sources[key[0]]/key[1]),'atr');h=wfdb.rdheader(str(sources[key[0]]/key[1]))
        mapping=set(zip(ann.sample.tolist(),ann.symbol))
        times=np.array([p/h.fs for p,s in zip(ann.sample,ann.symbol) if s in BEATS and 0<=p<h.sig_len])
        cache[key]=(mapping,times,h.fs)
    mapping,times,fs=cache[key];sample=int(row['sample']);symbol=row['symbol']
    assert (sample,symbol) in mapping and CLASSES[d['y'][i]]==symbol
    assert abs(int(row['center'])/FS-sample/fs)<=.5/FS+1e-9
    if symbol!='|':
        t=sample/fs;j=np.searchsorted(times,t)
        expected=np.log([max(t-times[j-1],.05),max(times[j+1]-t,.05)])
        np.testing.assert_allclose(d['r'][i,:2],expected,atol=1e-6)
        verified+=1
save(ROOT/'audit.json',{'passed':True,'targets_verified':len(rows),'true_beat_pre_post_rr_verified':verified,
     'group_disjoint':True,'anchor_and_padding_valid':True,'data_hash_matches':True,
     'scope':'original symbols/positions for all retained samples and true-beat pre/post RR; not medical boundary or model-performance verification'})
print('AUDIT_PASS',len(rows),verified)

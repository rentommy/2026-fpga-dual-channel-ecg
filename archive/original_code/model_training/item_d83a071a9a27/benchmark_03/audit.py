import csv,json
import numpy as np
import wfdb
from benchmark import ROOT,SOURCE,CLASSES,PRE,LENGTH,load,sha,dump

m=json.loads((ROOT/'data/manifest.json').read_text());d=load()
with open(ROOT/'data/beats.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
assert len(rows)==len(d['labels'])==100635
assert np.isfinite(d['physical']).all() and np.isfinite(d['warped']).all() and np.isfinite(d['rr']).all()
assert np.all(d['physical'][:,1,PRE]==1)
assert np.all(d['physical'][:,0][d['physical'][:,1]==0]==0)
np.testing.assert_allclose(d['physical'][:,0,PRE],d['warped'][:,0,PRE],atol=1e-6)
group_membership={};anns={};last={}
for i,r in enumerate(rows):
    assert int(r['index'])==i and CLASSES[d['labels'][i]]==r['symbol']
    point=int(r['sample']);lo=int(r['left']);hi=int(r['right']);rec=r['record']
    assert lo<=point<hi
    if rec in last:assert last[rec]<=lo
    last[rec]=hi
    group_membership.setdefault(r['group'],r['split']);assert group_membership[r['group']]==r['split']
    if rec not in anns:
        ann=wfdb.rdann(str(SOURCE/rec),'atr');anns[rec]=dict(zip(ann.sample,ann.symbol))
    assert anns[rec][point]==r['symbol']
    pos=point+np.arange(LENGTH)-PRE
    assert np.array_equal(d['physical'][i,1],(pos>=lo)&(pos<hi))
assert {r['split'] for r in rows if r['record'] in ('201','202')}.__len__()==1
assert sha(ROOT/'data/beats.npz')==m['array_sha256']
assert sha(ROOT/'data/beats.csv')==m['metadata_sha256']
assert sha(ROOT/'data/prepare_snapshot.py')==m['source_code_sha256']
dump(ROOT/'data/audit.json',{'n':len(rows),'original_labels_verified':True,'one_candidate_interval':True,
 'no_patient_group_overlap':True,'subject_201_202_together':True,'anchor_index_108':True,'padding_mask_verified':True,
 'arrays_finite':True,'data_and_prepare_snapshot_hashes_match':True})
print('All data provenance and physical-time checks PASS')

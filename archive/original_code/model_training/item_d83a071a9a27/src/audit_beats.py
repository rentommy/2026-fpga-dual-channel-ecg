"""Verify beat labels, cycle borders and record-contained context from saved artifacts."""
import csv,json
import numpy as np
from beat_project import ROOT,CLASSES,dump,sha

m=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'));total=0;eligible_count=0
for r in m['records']:
    p=ROOT/'data'/r['prefix'];wave=np.load(str(p)+'_wave.npy',mmap_mode='r')
    neigh=np.load(str(p)+'_neighbors.npy');labels=np.load(str(p)+'_labels.npy');eligible=np.load(str(p)+'_eligible.npy')
    assert wave.shape==(r['length'],256)
    assert np.all((neigh>=r['offset'])&(neigh<r['offset']+r['length']))
    assert np.all(neigh[:,1]==np.arange(r['offset'],r['offset']+r['length']))
    assert not eligible[0] and not eligible[-1]
    assert np.all(labels[eligible]>=0)
    ix=np.flatnonzero(eligible)[::max(1,int(eligible.sum()/128))]
    assert np.isfinite(wave[ix]).all()
    # float32 centering at large DC offsets leaves ~1e-5 residual; allow rounding only.
    assert np.allclose(wave[ix].mean(1),0,atol=2e-5)
    assert np.allclose(wave[ix].std(1),1,atol=1e-4)
    total+=len(wave);eligible_count+=int(eligible.sum())
with open(ROOT/'data/beats.csv',encoding='utf-8-sig',newline='') as f:
    previous_record=None;previous_right=None
    for i,row in enumerate(csv.DictReader(f)):
        assert int(row['index'])==i
        assert int(row['left_sample'])<=int(row['sample'])<int(row['right_sample'])
        if row['record_id']==previous_record:assert int(row['left_sample'])==previous_right
        previous_record=row['record_id'];previous_right=int(row['right_sample'])
        if int(row['eligible']):assert row['symbol']==CLASSES[int(row['label'])]
assert i+1==total==m['candidates']
assert sha(ROOT/'data/beats.csv')==m['metadata_sha256']
assert sha(ROOT/'data/prepare_snapshot.py')==m['prepare_code_sha256']
dump(ROOT/'data/audit.json',{'candidates':total,'eligible_targets':eligible_count,
  'one_raw_label_per_target':True,'nonoverlapping_borders':True,'context_within_record':True,
  'normalization_sample_check':True,'metadata_hash_matches':True,'prepare_snapshot_matches':True})
print('PASS',total,'candidates;',eligible_count,'eligible targets')

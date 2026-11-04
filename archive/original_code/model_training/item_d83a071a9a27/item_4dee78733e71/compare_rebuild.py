"""Verify row ordering against legacy CSV rather than infer it from row counts."""
from pathlib import Path
from collections import Counter
import csv,json
import numpy as np
from pipeline import ROOT,SOURCE,DATABASES,metadata,dump

def main():
    rows=metadata();shards=json.loads((ROOT/'data/shards.json').read_text());label_diffs=[];signal_stats=[]
    names=['0MLIII','1MLII','2ECG','3ECG']
    for (db,_),name in zip(DATABASES,names):
        subset=[r for r in rows if r['database']==db]
        with open(SOURCE/'Data'/f'{name}symbols_data.csv',encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f);next(reader);old=[r[0] for r in reader]
        assert len(old)==len(subset)
        transitions=Counter(f'{a} -> {b["label"]}' for a,b in zip(old,subset) if a!=b['label'])
        label_diffs.append({'database':db,'rows':len(old),'different_labels':sum(transitions.values()),'transitions':dict(transitions)})
        different=0;max_abs=0;count=0;cache={}
        with open(SOURCE/'Data'/f'{name}ecg_data.csv',encoding='utf-8') as f:
            next(f)
            for count,line in enumerate(f,1):
                r=subset[count-1];ix=int(r['index']);s=next(s for s in shards if s['offset']<=ix<s['offset']+s['length'])
                if s['file'] not in cache:cache[s['file']]=np.load(ROOT/'data'/s['file'],mmap_mode='r')
                new=cache[s['file']][ix-s['offset']];oldwave=np.fromstring(line,sep=',',dtype='float32')
                assert len(oldwave)==3600
                delta=float(np.max(np.abs(new-oldwave)))
                if not np.isfinite(delta):delta=float('inf')
                different+=int(delta>1e-6);max_abs=max(max_abs,delta)
        assert count==len(subset)
        signal_stats.append({'database':db,'rows':count,'different_waveforms_at_1e-6':different,'max_abs_difference':max_abs})
        print(db,label_diffs[-1],signal_stats[-1],flush=True)
    dump(ROOT/'audit/rebuild_comparison.json',{'label_comparison':label_diffs,'signal_comparison':signal_stats,
      'note':'Rowwise equality validates alignment for matching signals; label changes and nonfinite exclusion remain explicit.'})

if __name__=='__main__':main()

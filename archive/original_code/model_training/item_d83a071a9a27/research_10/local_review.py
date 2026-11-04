from pathlib import Path
import json
import numpy as np
ROOT=Path(__file__).resolve().parent

# Persist readable code cells without running notebooks or copying their rendered outputs.
for notebook in (ROOT/'sources').rglob('*.ipynb'):
    content=json.loads(notebook.read_text(encoding='utf-8'))
    blocks=[]
    for index,cell in enumerate(content.get('cells',[])):
        if cell.get('cell_type')=='code':blocks.append('# Notebook cell '+str(index)+'\n'+''.join(cell.get('source',[])))
    notebook.with_suffix('.code.txt').write_text('\n\n'.join(blocks),encoding='utf-8')

# Git trees API returns a tree-object SHA: label the provenance accurately.
for p in (ROOT/'sources').glob('*/provenance.json'):
    obj=json.loads(p.read_text(encoding='utf-8'))
    if 'commit' in obj:obj['git_tree_sha']=obj.pop('commit')
    obj['scope']='source snapshot only; upstream code not executed; tree SHA is not a verified commit SHA'
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

data=ROOT.parent/'experiment_09/data'
manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
rid=np.load(data/'record.npy',mmap_mode='r');split=np.load(data/'split.npy',mmap_mode='r')
labels=np.load(data/'y.npy',mmap_mode='r');wave=np.load(data/'x.npy',mmap_mode='r')
mit_ids=[r['id'] for r in manifest['records'] if r['db']=='mit']
ix=np.flatnonzero((split==1)&np.isin(rid,mit_ids));x=wave[ix]
left_ms=x[:,1,:77].sum(1)/256*1000
stats={}
for c,name in enumerate(manifest['classes']):
    keep=labels[ix]==c
    if not keep.any():continue
    stats[name]={'n':int(keep.sum()),'median_available_pre_center_ms':float(np.median(left_ms[keep])),
                 'less_than_200ms_fraction':float((left_ms[keep]<200).mean()),
                 'less_than_160ms_fraction':float((left_ms[keep]<160).mean()),
                 'less_than_100ms_fraction':float((left_ms[keep]<100).mean())}
result={'dataset':'experiment_09 MIT development validation','scope':'available pre-anchor context only; not clinical P-wave delineation or causal proof',
        'classes':stats}
(ROOT/'input_context_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

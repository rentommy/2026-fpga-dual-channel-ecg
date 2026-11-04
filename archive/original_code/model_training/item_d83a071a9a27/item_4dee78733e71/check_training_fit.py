"""Post-run sanity check on training only; no re-selection and no new test access."""
import csv,json,os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import numpy as np
import torch
from sklearn.metrics import classification_report
from pipeline import ROOT,CLASSES,metadata,dump,sha
from baseline_model import SENetLSTM

out=ROOT/'runs/record_baseline_seed0'
config=json.loads((out/'config.json').read_text())
assert config['pipeline_sha256']==sha(out/'pipeline_snapshot.py')
assert config['model_sha256']==sha(out/'model_snapshot.py')
meta=metadata()
with open(ROOT/'data/split_coverage.csv',encoding='utf-8-sig',newline='') as f:
    ix=np.array([int(r['index']) for r in csv.DictReader(f) if r['split']=='train'])
shards=json.loads((ROOT/'data/shards.json').read_text())
x=np.concatenate([np.load(ROOT/'data'/s['file']) for s in shards])[ix]
x-=x.mean(1,keepdims=True);x/=x.std(1,keepdims=True)+1e-8
y=np.array([CLASSES.index(meta[i]['label']) for i in ix])
model=SENetLSTM().cuda();ckpt=torch.load(out/'best.pt',weights_only=True);model.load_state_dict(ckpt['model_state_dict']);model.eval()
pred=[]
with torch.no_grad():
    for st in range(0,len(x),256):pred.extend(model(torch.from_numpy(x[st:st+256,None,:]).cuda()).argmax(1).cpu().tolist())
result={'scope':'training only, post-run sanity check; no re-selection','epoch':ckpt['epoch'],
        'accuracy':float((y==np.array(pred)).mean()),'report':classification_report(y,pred,labels=list(range(7)),target_names=CLASSES,output_dict=True,zero_division=0),
        'majority_N_accuracy':float((y==CLASSES.index('N')).mean()),'snapshot_hashes_match':True}
dump(out/'training_fit_check.json',result)
print(result['accuracy'],result['report']['macro avg']['f1-score'])

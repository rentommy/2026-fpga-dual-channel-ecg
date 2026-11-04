"""Reproduce w07 predictions on its original random-window test set for diagnosis only."""
import csv,json,os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import numpy as np
import torch
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import confusion_matrix
from baseline_model import SENetLSTM
from pipeline import ROOT,SOURCE,CLASSES,metadata,table,dump,analyze,sha

def main():
    torch.set_num_threads(8)
    rows=metadata();labels=[]
    for name in ['0MLIII','1MLII','2ECG','3ECG']:
        with open(SOURCE/'Data'/f'{name}symbols_data.csv',encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f);next(reader);labels.extend(r[0] for r in reader)
    assert len(labels)==len(rows)
    eligible=np.array([i for i,s in enumerate(labels) if s!='Q']);y=np.array([CLASSES.index(labels[i]) for i in eligible])
    _,te=next(StratifiedShuffleSplit(1,test_size=.1,train_size=.9,random_state=0).split(np.zeros(len(y)),y))
    ix=eligible[te]
    shards=json.loads((ROOT/'data/shards.json').read_text());cache={};waves=[]
    for i in ix:
        s=next(s for s in shards if s['offset']<=i<s['offset']+s['length'])
        if s['file'] not in cache:cache[s['file']]=np.load(ROOT/'data'/s['file'],mmap_mode='r')
        waves.append(cache[s['file']][i-s['offset']])
    x=np.array(waves,dtype='float32');x-=x.mean(1,keepdims=True);x/=x.std(1,keepdims=True)+1e-8
    path=SOURCE/'运行结果/7/save/best_w07.pt';ckpt=torch.load(path,map_location='cpu',weights_only=True)
    model=SENetLSTM();model.load_state_dict(ckpt['model_state_dict']);model.eval();pred=[];prob=[]
    with torch.no_grad():
        for start in range(0,len(x),256):
            logits=model(torch.from_numpy(x[start:start+256,None,:]));pred.extend(logits.argmax(1).tolist());prob.extend(logits.softmax(1)[:,0].tolist())
    out=ROOT/'audit/historical_w07';out.mkdir(exist_ok=True)
    predictions=[{**rows[i],'label':labels[i],'prediction':CLASSES[p],'prob_A':pa,'correct':int(labels[i]==CLASSES[p])} for i,p,pa in zip(ix,pred,prob)]
    table(out/'val_predictions.csv',predictions)
    # Reuse stratification only. Here val is a filename convention, NOT an independent validation set.
    analyze(out)
    cm=confusion_matrix(y[te],pred,labels=list(range(7)))
    expected=np.array([[83,0,0,72,1,6,2],[0,520,0,1,0,4,1],[0,0,63,0,2,2,0],
                       [52,0,0,9114,0,98,115],[2,0,1,2,59,0,0],[0,1,0,61,0,1072,20],[1,0,1,101,0,23,347]])
    result={'scope':'original w07 random-window test; historical diagnostic, not independent validation',
       'checkpoint_sha256':sha(path),'confusion_matrix':cm.tolist(),'expected_confusion_matrix':expected.tolist(),
       'exact_confusion_match':bool(np.array_equal(cm,expected)),'accuracy':float(np.trace(cm)/cm.sum())}
    dump(out/'reproduction.json',result)
    analysis=json.loads((out/'analysis.json').read_text(encoding='utf-8'));analysis['scope']=result['scope'];dump(out/'analysis.json',analysis)
    print(json.dumps(result,indent=2));print(json.dumps(analysis['strata'][:3],indent=2))

if __name__=='__main__':main()

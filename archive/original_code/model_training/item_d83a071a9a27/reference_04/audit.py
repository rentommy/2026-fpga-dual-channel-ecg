from pathlib import Path
import json,hashlib
import numpy as np
import torch
from sklearn.metrics import f1_score
from models import BeatModel
ROOT=Path(__file__).resolve().parent
torch.set_num_threads(8)
protocol=json.loads((ROOT/'protocol.json').read_text())
source=ROOT.parent/'benchmark_03/data/beats.npz'
assert hashlib.sha256(source.read_bytes()).hexdigest()==protocol['source_sha256']
d=np.load(source);old=['A','B','F','L','N','R','S','V','|'];classes=protocol['classes'];lookup=np.array([classes.index(c) if c in classes else -1 for c in old]);y=lookup[d['labels']]
va=np.flatnonzero((d['split']==1)&(y>=0));tr=np.flatnonzero((d['split']==0)&(y>=0))
assert len(tr)==protocol['train_count'] and len(va)==protocol['val_count']
assert not(set(d['record'][tr])&set(d['record'][va]))
rr=np.clip((d['rr'][va]-np.array(protocol['rr_mean']))/np.array(protocol['rr_std']),-8,8).astype('float32')
device=torch.device('cuda' if torch.cuda.is_available() else 'cpu');verified=[]
for kind in protocol['models']:
    folder=ROOT/'runs'/kind;m=BeatModel(kind).to(device);m.load_state_dict(torch.load(folder/'best.pt',map_location=device,weights_only=True));m.eval();pred=[]
    with torch.no_grad():
        for start in range(0,len(va),256):
            logits=m(torch.tensor(d['warped'][va[start:start+256]],device=device),torch.tensor(rr[start:start+256],device=device))
            assert logits.shape[1]==7 and torch.isfinite(logits).all()
            pred.extend(logits.argmax(1).cpu().tolist())
    np.testing.assert_array_equal(pred,np.load(folder/'val_predictions.npy'))
    score=f1_score(y[va],pred,average='macro',labels=list(range(7)),zero_division=0)
    assert abs(score-json.loads((folder/'val_metrics.json').read_text())['macro_f1'])<1e-12
    verified.append(kind)
result={'passed':True,'classes':classes,'verified_saved_models':verified,'all_validation_predictions_reproduced':True,'metrics_recomputed':True,'data_hash_matches':True,'test_evaluated':False}
(ROOT/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)

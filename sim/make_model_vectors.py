"""Generate synthetic portable-model fixtures; contains no personal ECG."""
from pathlib import Path
import sys,json
import numpy as np
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'board/runtime'))
from ecg_model import BeatModel
folder=r/'board/runtime/model';m=BeatModel(folder);rng=np.random.default_rng(20261104)
x=rng.normal(0,1,(4,2,205)).astype('float32');x[:,1,:]=1
rr=rng.uniform(-1,1,(4,8)).astype('float32');logits=np.array([m(a,b) for a,b in zip(x,rr)])
np.savez(folder/'synthetic_inputs.npz',x=x,rr=rr,logits=logits)
(folder/'synthetic_reference.json').write_text(json.dumps({'source':'seeded synthetic model inputs; not ECG accuracy evidence','classes':m.config['classes'] if hasattr(m,'config') else json.loads((folder/'config.json').read_text())['classes'],'samples':4},indent=2),encoding='utf8')
print('SYNTHETIC_MODEL_VECTORS_READY')

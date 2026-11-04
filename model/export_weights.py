"""Re-export the selected checkpoint and compare NumPy with PyTorch on synthetic inputs."""
from pathlib import Path
import sys,json,numpy as np,torch
from torch import nn
from network import Network
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'board/runtime'))
from ecg_model import BeatModel
torch.set_num_threads(2)
state=torch.load(r/'model/selected/best.pt',map_location='cpu',weights_only=True)
m=Network('multi');m.head[-1]=nn.Linear(64,8);m.load_state_dict(state,strict=True);m.eval()
folder=r/'board/runtime/model';np.savez(folder/'weights.npz',**{k:v.numpy() for k,v in state.items()})
portable=BeatModel(folder);data=np.load(folder/'synthetic_inputs.npz');errors=[];logits=[]
for x,rr in zip(data['x'],data['rr']):
 with torch.no_grad():expected=m(torch.from_numpy(x[None]),torch.from_numpy(rr[None])).numpy()[0]
 actual=portable(x,rr);error=float(np.max(np.abs(actual-expected)));assert error<2e-4 and actual.argmax()==expected.argmax();errors.append(error);logits.append(expected)
np.savez(folder/'synthetic_inputs.npz',x=data['x'],rr=data['rr'],logits=np.array(logits))
result={'passed':True,'samples':len(errors),'max_logit_error':max(errors),'reference':'PyTorch selected checkpoint; synthetic inputs, not clinical accuracy'}
(r/'report/evidence/synthetic_model_export.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))

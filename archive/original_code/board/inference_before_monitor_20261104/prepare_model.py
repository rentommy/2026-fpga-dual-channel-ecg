"""Export the selected state_dict and validate portable inference against torch."""
import ast,json,hashlib,time,sys
from pathlib import Path
import numpy as np
import torch
from torch import nn
from ecg_model import BeatModel,preprocess,detect_beats,beat_input

root=Path(__file__).resolve().parents[2]
run=root/'模型训练/模型改进/experiment_09/runs/six_db_seed0'
output=Path(__file__).resolve().parent/'model';output.mkdir(exist_ok=True)
torch.set_num_threads(2)
namespace={'torch':torch,'nn':nn}
tree=ast.parse((root/'模型训练/模型改进/experiment_08/run.py').read_text(encoding='utf-8'))
for node in tree.body:
    if isinstance(node,ast.ClassDef) and node.name in ['Residual','Network']:
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<network>','exec'),namespace)
m=namespace['Network']('multi');m.head[-1]=nn.Linear(64,8)
state=torch.load(run/'best.pt',map_location='cpu',weights_only=True);m.load_state_dict(state,strict=True);m.eval()
np.savez(output/'weights.npz',**{k:v.numpy() for k,v in state.items()})
config=json.loads((run/'config.json').read_text());(output/'config.json').write_text(json.dumps(config,indent=2))
portable=BeatModel(output)
records=root/'模型训练/采集/2026-11-04_真实心电_已保存记录/01_板端原始文件'
all_x=[];all_r=[];all_logits=[];items=[]
for folder,ch in [('electrode_cn2_20261104',1),('electrode_cn4_rld1_20261104',0)]:
    raw=np.load(records/folder/'raw.npy')[:,ch]
    y=preprocess(raw*(2.42/6/(2**23-1)*1000));times=detect_beats(y)
    np.save(output/(folder+'_filtered256.npy'),y)
    for j in range(1,len(times)-1):
        x,r=beat_input(y,times,j,config)
        with torch.no_grad():logits=m(torch.from_numpy(x[None]),torch.from_numpy(r[None])).numpy()[0]
        actual=portable(x,r)
        error=float(np.max(np.abs(actual-logits)))
        assert error<2e-4,(folder,j,error)
        p=np.exp(logits-logits.max());p/=p.sum()
        all_x.append(x);all_r.append(r);all_logits.append(logits)
        items.append(dict(recording=folder,channel=ch+1,anchor_nominal_s=float(times[j]),
                          next_beat_nominal_s=float(times[j+1]),label=config['classes'][int(p.argmax())],
                          score=float(p.max()),probabilities=p.tolist(),numpy_max_logit_error=error,
                          annotation='automatic_R_peak; no expert ground truth'))
np.savez(output/'replay_inputs.npz',x=np.array(all_x),rr=np.array(all_r),logits=np.array(all_logits))
manifest=dict(weight_sha256=hashlib.sha256((run/'best.pt').read_bytes()).hexdigest(),
              config_sha256=hashlib.sha256((run/'config.json').read_bytes()).hexdigest(),
              classes=config['classes'],input_shape=[2,205],rr_shape=[8],fs=256,
              parameters=sum(p.numel() for p in m.parameters()),beats=len(items),
              max_numpy_logit_error=max(i['numpy_max_logit_error'] for i in items),
              records=items,performance_note='Desktop reference only; no clinical accuracy labels')
(output/'reference_results.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k!='records'},ensure_ascii=False,indent=2))

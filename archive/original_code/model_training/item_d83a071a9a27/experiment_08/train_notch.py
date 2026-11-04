import numpy as np
import torch
from run import ROOT,save,Network,sha,metrics
from normalize_study import fit,normalize
from compare import report

if __name__=='__main__':
    import json
    assert json.loads((ROOT/'controlled_comparison_audit.json').read_text())['passed']
    save(ROOT/'protocol.json',{'filter':'native fs: butter order3 0.5-40Hz sosfiltfilt -> iirnotch 50Hz Q30 -> tf2sos -> sosfiltfilt',
         'seeds':[0,1,2],'model':'multi','training':'MIT + INCART original training patients','normalization':'per-beat valid-point mean/std',
         'comparison':'experiment_07/multi_z_mixed same numbered seeds','selection':'MIT validation macro-F1, same 30 epochs/patience7',
         'external_test':'not rerun','filter_sha256':sha(ROOT/'filtering.py')})
    for seed in [0,1,2]:fit('multi',True,seed)
    # Reload each checkpoint and reproduce its saved MIT validation predictions.
    with np.load(ROOT/'data/beats.npz') as d:
        ix=np.flatnonzero((d['db']=='mit')&(d['split']=='val'))
        x=normalize(d['x'][ix]);rr=d['r'][ix];y=d['y'][ix]
    torch.set_num_threads(8)
    for seed in [0,1,2]:
        folder=ROOT/'runs'/f'multi_z_mixed_seed{seed}';cfg=json.loads((folder/'config.json').read_text())
        r=np.clip((rr-np.array(cfg['rr_mean'],dtype=np.float32))/np.array(cfg['rr_std'],dtype=np.float32),-8,8)
        m=Network('multi').cuda();m.load_state_dict(torch.load(folder/'best.pt',weights_only=True));m.eval()
        with torch.no_grad():
            pred=np.concatenate([m(torch.tensor(x[i:i+512],device='cuda'),torch.tensor(r[i:i+512],device='cuda')).argmax(1).cpu().numpy() for i in range(0,len(y),512)])
        assert np.array_equal(pred,np.load(folder/'val_predictions.npy'))
    save(ROOT/'checkpoint_audit.json',{'passed':True,'seeds':[0,1,2],'validation_predictions_reproduced':True})
    report();print('NOTCH_EXPERIMENT_COMPLETE',flush=True)

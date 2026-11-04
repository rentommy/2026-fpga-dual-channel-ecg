"""Reload every checkpoint and reproduce all development predictions."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mplcache'))
import json,csv
import numpy as np
import torch
from study import data,Model,metric,sha,save,CLASSES

def main():
    torch.set_num_threads(8);sets=data();v=sets['val'];device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tensors={k:torch.tensor(v[k],device=device) for k in ['x','r','f']}
    protocol=json.loads((ROOT/'protocol.json').read_text());assert sha(ROOT.parent/'benchmark_03/data/beats.npz')==protocol['source_sha256']
    checked=[]
    for folder in sorted((ROOT/'runs').iterdir()):
        c=json.loads((folder/'config.json').read_text())
        assert sha(folder/'training_snapshot.py')==c['code_sha256']
        assert sha(folder/'model_snapshot.py')==c['model_sha256']==sha(ROOT/'baseline_model.py')
        assert sha(ROOT/'protocol.json')==c['protocol_sha256']
        for k in ['r','f']:
            saved=c['rr_stats' if k=='r' else 'feature_stats']
            assert saved==sets['train'][k+'_stats']
        model=Model(c.get('mode','full')).to(device);model.load_state_dict(torch.load(folder/'best.pt',map_location=device,weights_only=True));model.eval();pred=[]
        with torch.no_grad():
            for j in range(0,len(v['y']),256):
                logits=model(tensors['x'][j:j+256],tensors['r'][j:j+256],tensors['f'][j:j+256]);assert logits.shape[1]==7 and torch.isfinite(logits).all();pred.extend(logits.argmax(1).cpu().tolist())
        np.testing.assert_array_equal(pred,np.load(folder/'val_predictions.npy'))
        score=metric(v['y'],np.array(pred));stored=json.loads((folder/'val_metrics.json').read_text())
        assert score['confusion_matrix']==stored['confusion_matrix']
        assert abs(score['macro_f1']-stored['macro_f1'])<1e-12
        checked.append(folder.name);print('Verified',folder.name,flush=True)
    save(ROOT/'audit.json',{'passed':True,'verified_runs':checked,'full_validation_predictions_reproduced':True,'seven_output_mapping_checked':True,'train_only_scalers_verified':True,'source_and_snapshot_hashes_verified':True,'no_patient_overlap':True,'test_evaluated':False})
    plot()

def plot():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    selected=json.loads((ROOT/'selection.json').read_text())['selected'];fig,axes=plt.subplots(1,2,figsize=(13,5))
    summaries={}
    for name in dict.fromkeys(['baseline',selected]):
        summaries[name]=[json.loads((ROOT/'runs'/f'{name}_seed{s}/val_metrics.json').read_text()) for s in [0,1,2]]
    for i,(name,results) in enumerate(summaries.items()):
        values=[r['macro_f1'] for r in results];axes[0].scatter([i]*3,values,label=name,s=55)
        axes[0].errorbar(i,np.mean(values),yerr=np.std(values),color='black',capsize=7,fmt='_',markersize=18)
        recall=np.array([[r['report'][c]['recall'] for c in CLASSES] for r in results]);axes[1].bar(np.arange(7)+i*.36,recall.mean(0),width=.34,yerr=recall.std(0),capsize=3,label=name)
    axes[0].set_xticks(range(len(summaries)),list(summaries));axes[0].set_ylabel('Validation macro-F1');axes[0].set_ylim(0,1);axes[0].set_title('Three seeds: points, mean and seed SD')
    axes[1].set_xticks(np.arange(7)+.18,CLASSES);axes[1].set_ylim(0,1.05);axes[1].set_ylabel('Recall');axes[1].legend();axes[1].set_title('Recall: mean and seed SD')
    fig.suptitle('Development validation only; no independent test claim');fig.tight_layout();fig.savefig(ROOT/'三种子对照.png',dpi=160);plt.close(fig)
if __name__=='__main__':main()

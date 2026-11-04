import os,json
import numpy as np
from beat_project import ROOT,CLASSES
os.environ['MPLCONFIGDIR']=str(ROOT/'data/.matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

m=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'));found={}
for r in m['records']:
    if r['split']!='train':continue
    base=ROOT/'data'/r['prefix'];labels=np.load(str(base)+'_labels.npy');eligible=np.load(str(base)+'_eligible.npy')
    for j,c in enumerate(CLASSES):
        if c in found:continue
        ix=np.flatnonzero(eligible&(labels==j))
        if len(ix):
            k=ix[0];wave=np.load(str(base)+'_wave.npy',mmap_mode='r')[k];rr=np.load(str(base)+'_rr.npy',mmap_mode='r')[k]
            found[c]=(r,k,wave.copy(),rr.copy())
fig,axes=plt.subplots(3,3,figsize=(13,9))
for ax,c in zip(axes.flat,CLASSES):
    r,k,w,rr=found[c];duration=np.exp(rr[7])*1000
    ax.plot(np.linspace(0,duration,256),w,linewidth=.9);ax.axvline(rr[6]*duration,color='red',alpha=.5)
    ax.set_title(f"Target {c}: record {r['record']}, candidate {k}\npre={np.exp(rr[0]):.2f}s, post={np.exp(rr[1]):.2f}s",fontsize=9)
    ax.set_xlabel('within-cycle time (ms)');ax.set_ylabel('normalized amplitude')
fig.suptitle('One candidate cycle = one original label; red = annotated target position')
fig.tight_layout();fig.savefig(ROOT/'data/单拍预处理样例.png',dpi=150)

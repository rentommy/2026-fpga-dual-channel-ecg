import os,csv
import numpy as np
from benchmark import ROOT,CLASSES,PRE,FS,load
os.environ['MPLCONFIGDIR']=str(ROOT/'data/.matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
d=load()
with open(ROOT/'data/beats.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
fig,axes=plt.subplots(4,2,figsize=(12,10))
for axrow,c in zip(axes,['A','L','R','V']):
    i=np.flatnonzero((d['labels']==CLASSES.index(c))&(d['split']==0))[0]
    for ax,mode in zip(axrow,['physical','warped']):
        x=(np.arange(288)-PRE)/FS*1000 if mode=='physical' else np.arange(288)-PRE
        ax.plot(x,d[mode][i,0],linewidth=1)
        if mode=='physical':ax.fill_between(x,ax.get_ylim()[0],ax.get_ylim()[1],where=d[mode][i,1]==0,color='grey',alpha=.15)
        ax.axvline(0,color='red',linewidth=.7)
        ax.set_title(f'{c}, record {rows[i]["record"]}, {mode}')
        ax.set_xlabel('real time relative to target (ms)' if mode=='physical' else 'normalized sample index relative to target')
fig.suptitle('Same target, same label; left preserves time, right scales the cycle')
fig.tight_layout();fig.savefig(ROOT/'data/预处理对照.png',dpi=140)

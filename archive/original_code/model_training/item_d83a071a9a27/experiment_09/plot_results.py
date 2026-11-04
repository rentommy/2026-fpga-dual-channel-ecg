import os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(ROOT/'.matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

results=json.loads((ROOT/'evaluation.json').read_text(encoding='utf-8'))
classes=['A','F','L','N','R','S','V','|'];labels=classes[:-1]+['Artifact']
fig,axes=plt.subplots(1,2,figsize=(12,4.5))
for ax,db,split in zip(axes,['mit','all'],['val','test']):
    for j,arm in enumerate(['two_db','six_db']):
        rows=[r for r in results if r['arm']==arm and r['db']==db and r['split']==split]
        values=np.array([[r['report'][c]['recall']*100 for c in classes] for r in rows])
        mean=values.mean(0);sd=values.std(0)
        for k,c in enumerate(classes):
            if rows[0]['report'][c]['support']==0:mean[k]=np.nan;sd[k]=np.nan
        ax.bar(np.arange(8)+(j-.5)*.36,mean,width=.34,yerr=sd,capsize=3,label=arm)
    if db=='mit':ax.text(5,3,'N/A',ha='center',color='gray',fontsize=9)
    ax.set_xticks(range(8),labels);ax.set_ylim(0,105);ax.set_ylabel('Recall (%)');ax.set_title(db+'/'+split)
    ax.axhline(80,color='gray',ls='--',lw=1);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axes[0].legend();fig.suptitle('Eight original outputs | Three seeds | Error bars: seed SD')
fig.tight_layout();fig.savefig(ROOT/'recall_comparison.png',dpi=180)
print('Plot saved')

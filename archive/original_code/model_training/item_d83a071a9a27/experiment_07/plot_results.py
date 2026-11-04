import os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(ROOT/'.matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

results=json.loads((ROOT/'evaluation.json').read_text(encoding='utf-8'))
winner=json.loads((ROOT/'selection.json').read_text())['winner'].rsplit('_seed',1)[0]
names=list(dict.fromkeys(['baseline_z_mit',winner]))
labels=['A','F','L','N','R','V','Artifact']
keys=['A','F','L','N','R','V','|']
fig,axes=plt.subplots(1,2,figsize=(12,4.5))
colors=['#55748f','#dc7a34']
for j,name in enumerate(names):
    rows=[v for v in results if v['name']==name and v['dataset']=='mit']
    for ax,key in zip(axes,['precision','recall']):
        values=np.array([[r['report'][c][key]*100 for c in keys] for r in rows])
        ax.bar(np.arange(7)+(j-.5)*.36,values.mean(0),width=.34,yerr=values.std(0),capsize=3,label=name,color=colors[j])
        ax.set_xticks(range(7),labels);ax.set_ylim(0,105);ax.set_ylabel(key.capitalize()+' (%)');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axes[0].legend(fontsize=8);axes[1].axhline(80,ls='--',color='gray',lw=1)
fig.suptitle('MIT development patients | 3 seeds | error bars: seed SD')
fig.tight_layout();fig.savefig(ROOT/'per_class_comparison.png',dpi=180);plt.close(fig)
print('Plot saved')

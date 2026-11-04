"""Export frozen test confusion matrix; no fitting."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from benchmark import ROOT, CLASSES

r=json.loads((ROOT/'final/ensemble_metrics.json').read_text())
cm=np.array(r['confusion_matrix']);total=cm.sum(1)
rate=np.divide(cm,total[:,None],out=np.zeros_like(cm,dtype=float),where=total[:,None]>0)
fig,ax=plt.subplots(figsize=(9,7))
im=ax.imshow(rate,vmin=0,vmax=1,cmap='Blues')
ax.set_xticks(range(9),CLASSES);ax.set_yticks(range(9),[f'{c} (n={n})' for c,n in zip(CLASSES,total)])
for i in range(9):
    for j in range(9):
        text='NA' if total[i]==0 else f'{rate[i,j]:.0%}'
        ax.text(j,i,text,ha='center',va='center',fontsize=9,color='white' if rate[i,j]>.5 else 'black')
ax.set_xlabel('Predicted raw symbol');ax.set_ylabel('True raw symbol')
ax.set_title('Frozen MIT-BIH MLII test: three-seed CNN ensemble\nRow-normalized; B and S have no test support')
fig.colorbar(im,ax=ax,label='Fraction of true class')
fig.tight_layout();fig.savefig(ROOT/'final/confusion_matrix.png',dpi=170);plt.close(fig)
print('Frozen test matrix exported.')

from pathlib import Path
import numpy as np
r=Path(__file__).resolve().parents[1]
t=np.arange(30000)/500.;phase=t%0.82
x=21000*np.exp(-.5*((phase-.3)/.009)**2)-6500*np.exp(-.5*((phase-.326)/.015)**2)+6200*np.exp(-.5*((phase-.53)/.065)**2)+1500*np.sin(2*np.pi*.2*t)+800*np.sin(2*np.pi*50*t)
p=r/'data/source/ecg_60s_500sps.txt';p.parent.mkdir(parents=True,exist_ok=True);np.savetxt(p,np.rint(x).astype(int),fmt='%d')
print('Generated synthetic 60-second input, not human ECG')

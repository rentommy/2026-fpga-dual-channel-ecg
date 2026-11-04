"""Run on PYNQ only after stopping ecg-scope.service; programs the overlay."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import json,time,numpy as np
from pynq import Overlay
from ecg_model import BeatModel,FPGAConv
root=Path(__file__).resolve().parent
ol=Overlay(str(root/'overlay/ecg_inference.bit'))
m=BeatModel(root/'model');conv=FPGAConv(ol.ecg_conv_0,m.w);m.conv_engine=conv
data=np.load(root/'model/synthetic_inputs.npz');errors=[]
try:
 for x,rr,expected in zip(data['x'],data['rr'],data['logits']):
  actual=m(x,rr);errors.append(float(np.max(np.abs(actual-expected))))
  assert errors[-1]<5e-4 and actual.argmax()==expected.argmax()
 print(json.dumps({'passed':True,'samples':len(errors),'max_logit_error':max(errors),'source':'synthetic model inputs; not clinical accuracy'}))
finally:conv.close()

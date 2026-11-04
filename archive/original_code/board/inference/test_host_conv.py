import ctypes,json,os,time
from pathlib import Path
import numpy as np
from ecg_model import BeatModel

root=Path(__file__).resolve().parents[2]
os.add_dll_directory('D:/msys64/ucrt64/bin')
lib=ctypes.CDLL(str(root/'build/ecg_conv_host.dll'))
ptr=np.ctypeslib.ndpointer(dtype=np.float32,flags='C_CONTIGUOUS')
lib.ecg_conv.argtypes=[ptr,ptr,ptr,ptr,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int]
def conv(x,w,b,dilation=1,name=None):
    x=np.ascontiguousarray(x,dtype=np.float32);w=np.ascontiguousarray(w,dtype=np.float32);b=np.ascontiguousarray(b,dtype=np.float32)
    out=np.empty((len(w),205),np.float32)
    lib.ecg_conv(x,w,b,out,x.shape[0],w.shape[0],w.shape[2],dilation)
    return out
folder=Path(__file__).parent/'model'
test=np.load(folder/'replay_inputs.npz')
m=BeatModel(folder,conv)
errors=[];pred=[];begin=time.monotonic()
for x,rr,expected in zip(test['x'],test['rr'],test['logits']):
    logits=m(x,rr);errors.append(float(np.max(np.abs(logits-expected))));pred.append(int(logits.argmax()))
assert max(errors)<2e-4,max(errors)
assert np.array_equal(pred,test['logits'].argmax(1))
summary=dict(passed=True,beats=len(errors),all_classes_match=True,max_logit_error=max(errors),elapsed_host_seconds=time.monotonic()-begin,note='C kernel host execution, not FPGA timing or RTL equivalence')
(folder/'host_conv_test.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))

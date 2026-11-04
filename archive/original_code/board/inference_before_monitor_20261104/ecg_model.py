"""Experiment 09 inference without a board-side PyTorch dependency."""
import time
from pathlib import Path
import numpy as np

def cpu_conv(x,w,b,dilation=1):
    k=w.shape[-1];pad=(k-1)*dilation//2
    windows=np.lib.stride_tricks.sliding_window_view(np.pad(x,((0,0),(pad,pad))),
                                                    (k-1)*dilation+1,axis=1)[:,:,::dilation]
    columns=windows.transpose(1,0,2).reshape(x.shape[-1],-1)
    return np.ascontiguousarray((columns@w.reshape(len(w),-1).T+b).T,dtype=np.float32)

class FPGAConv:
    def __init__(self,ip,weights):
        from pynq import allocate
        self.ip=ip;self.calls=0;self.seconds=0
        self.input=allocate((128*205,),dtype=np.float32)
        self.output=allocate((128*205,),dtype=np.float32)
        self.params={}
        for name,w in weights.items():
            if name.endswith('.weight') and w.ndim==3:
                wb=allocate(w.shape,dtype=np.float32);wb[:]=w;wb.flush()
                bias=allocate((w.shape[0],),dtype=np.float32);bias[:]=weights[name[:-6]+'bias'];bias.flush()
                self.params[name[:-7]]=(wb,bias)
    def __call__(self,x,w,b,dilation=1,name=None):
        if x.shape[1]!=205 or not np.isfinite(x).all():raise ValueError('Invalid convolution input')
        cin=x.shape[0];cout,k=w.shape[0],w.shape[2]
        wb,bb=self.params[name]
        self.input[:x.size]=x.reshape(-1);self.input.flush()
        for offset,buf in [(0x10,self.input),(0x1c,wb),(0x28,bb),(0x34,self.output)]:
            address=int(buf.physical_address);self.ip.write(offset,address&0xffffffff);self.ip.write(offset+4,address>>32)
        for offset,value in [(0x40,cin),(0x48,cout),(0x50,k),(0x58,dilation)]:self.ip.write(offset,value)
        begin=time.monotonic();self.ip.write(0,1)
        while not self.ip.read(0)&2:
            if time.monotonic()-begin>5:raise TimeoutError('FPGA convolution timeout')
            time.sleep(.0001)
        self.output.invalidate();self.calls+=1;self.seconds+=time.monotonic()-begin
        return self.output[:cout*205].copy().reshape(cout,205)
    def close(self):
        self.input.freebuffer();self.output.freebuffer()
        for w,b in self.params.values():w.freebuffer();b.freebuffer()

class BeatModel:
    def __init__(self,folder,conv=None):
        self.w=dict(np.load(Path(folder)/'weights.npz',allow_pickle=False))
        self.conv_engine=conv;self.trace={}
    def conv(self,x,name,d=1):
        w,b=self.w[name+'.weight'],self.w[name+'.bias']
        y=self.conv_engine(x,w,b,d,name=name) if self.conv_engine else cpu_conv(x,w,b,d)
        self.trace[name]=y.copy()
        return y
    def norm(self,x,name):
        groups=x.reshape(4,-1);mean=groups.mean(1,keepdims=True)
        v=groups-mean;var=(v*v).mean(1,keepdims=True)
        z=(v/np.sqrt(var+np.float32(1e-5))).reshape(x.shape)
        return z*self.w[name+'.weight'][:,None]+self.w[name+'.bias'][:,None]
    def linear(self,x,name):return self.w[name+'.weight']@x+self.w[name+'.bias']
    def __call__(self,x,rr):
        self.trace={}
        z=np.concatenate([np.maximum(self.conv(x,'branches.'+str(i)),0) for i in range(3)])
        for block,d in enumerate([1,2,4]):
            prefix='body.'+str(block)
            skip=self.conv(z,prefix+'.skip')
            y=np.maximum(self.norm(self.conv(z,prefix+'.net.0',d),prefix+'.net.1'),0)
            y=self.norm(self.conv(y,prefix+'.net.3'),prefix+'.net.4')
            z=np.maximum(y+skip,0)
        pooled=(z*x[1:2]).sum(1)/max(float(x[1].sum()),1)
        gate=self.linear(np.maximum(self.linear(pooled,'gate.0'),0),'gate.2')
        pooled=pooled/(1+np.exp(-gate))
        r=np.maximum(self.linear(rr,'rr.0'),0)
        return self.linear(np.maximum(self.linear(np.concatenate([pooled,r]),'head.0'),0),'head.3')

def beat_input(filtered256,times,j,config):
    t=times[j];prev,nxt=times[j-1],times[j+1]
    before,after=t-prev,nxt-t
    prior=np.diff(times[max(0,j-8):j+1]);last=prior[-2] if len(prior)>1 else before
    center=int(np.rint(t*256));lo=int(np.ceil((prev+t)*128));hi=int(np.ceil((t+nxt)*128))
    pos=center+np.arange(205)-77
    mask=(pos>=lo)&(pos<hi)&(pos>=0)&(pos<len(filtered256))
    if not mask[77] or mask.sum()<16:raise ValueError('Insufficient valid beat samples')
    v=filtered256[pos[mask]];sd=v.std()
    if sd<1e-6:raise ValueError('Flat input')
    z=np.zeros(205,np.float32);z[mask]=(v-v.mean())/sd
    a,b,ref=max(before,.05),max(after,.05),max(float(np.median(prior)),.05)
    rr=np.array([np.log(a),np.log(b),min(a/ref,5),min(b/ref,5),np.log(ref),min(a/b,5),
                 np.log((hi-lo)/256),np.log(max(last,.05))],np.float32)
    rr=np.clip((rr-np.asarray(config['rr_mean'],np.float32))/np.asarray(config['rr_std'],np.float32),-8,8)
    return np.stack([z,mask]).astype(np.float32),rr.astype(np.float32)

def preprocess(raw,fs=500):
    from scipy import signal
    sos=signal.butter(3,[.5,40],btype='bandpass',fs=fs,output='sos')
    y=signal.sosfiltfilt(sos,np.asarray(raw,dtype=np.float64))
    b,a=signal.iirnotch(50,30,fs=fs)
    y=signal.sosfiltfilt(signal.tf2sos(b,a),y)
    return signal.resample_poly(y,256,fs)

def detect_beats(filtered256):
    from scipy.signal import find_peaks
    a=filtered256
    stable=a[512:-256] if len(a)>1024 else a
    lo,hi=np.percentile(stable,[.5,99.5]);polarity=1 if abs(hi)>=abs(lo) else -1
    prominence=max(.12,float(np.percentile(np.abs(stable),99))*.3)
    peaks,_=find_peaks(a*polarity,distance=round(.28*256),prominence=prominence)
    return peaks[(peaks>=512)&(peaks<len(a)-256)]/256

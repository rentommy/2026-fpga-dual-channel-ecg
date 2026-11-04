"""Bounded, asynchronous, delayed beat recognition. No FPGA overlay reload in worker."""
import json,multiprocessing as mp,queue,time
from pathlib import Path
import numpy as np

def recognize_snapshot(model,accelerator,config,job,last_anchor):
    from ecg_model import preprocess,detect_beats,beat_input
    gen,ch,start,raw=job
    begin=time.monotonic();filtered=preprocess(raw.astype(float)*(2.42/6/(2**23-1)*1000))
    times=detect_beats(filtered);end_sample=start+len(raw)
    candidates=[int(start+round(t*500)) for t in times]
    emitted=[]
    for j in range(1,len(times)-1):
        anchor=int(start+round(times[j]*500))
        if anchor<=last_anchor+100 or times[j]>len(raw)/500-2.0:continue
        try:x,rr=beat_input(filtered,times,j,config)
        except ValueError:continue
        inference_start=time.monotonic();conv_start=accelerator.seconds;calls_start=accelerator.calls
        logits=model(x,rr);p=np.exp(logits-logits.max());p/=p.sum()
        emitted.append(dict(source_sample=anchor,channel=ch,label=config['classes'][int(p.argmax())],
            confidence=float(p.max()),probabilities=p.tolist(),inference_seconds=time.monotonic()-inference_start,
            fpga_conv_seconds=accelerator.seconds-conv_start,fpga_conv_calls=accelerator.calls-calls_start,
            available_through_sample=end_sample,buffer_wait_seconds=(end_sample-anchor)/500,
            processing_seconds=time.monotonic()-begin))
        last_anchor=anchor
    return dict(generation=gen,channel=ch,candidates=candidates,beats=emitted,
                processing_seconds=time.monotonic()-begin),last_anchor

def worker_loop(jobs,results,address,span,folder):
    from pynq import MMIO
    from ecg_model import BeatModel,FPGAConv
    model=BeatModel(folder)
    accelerator=FPGAConv(MMIO(address,span),model.w);model.conv_engine=accelerator
    config=json.loads((Path(folder)/'config.json').read_text())
    generation=None;last_anchor=-1e9
    try:
        while True:
            job=jobs.get()
            if job is None:break
            while True:
                try:
                    newest=jobs.get_nowait()
                    if newest is None:return
                    job=newest
                except queue.Empty:break
            gen=job[0]
            if gen!=generation:generation=gen;last_anchor=-1e9
            message,last_anchor=recognize_snapshot(model,accelerator,config,job,last_anchor)
            try:results.put_nowait(message)
            except queue.Full:
                results.get_nowait();results.put_nowait(message)
    except Exception as exc:
        results.put(dict(error=type(exc).__name__+': '+str(exc)))
        raise
    finally:accelerator.close()

class StreamRecognizer:
    def __init__(self,overlay,folder,status_file):
        ip=overlay.ip_dict['ecg_conv_0']
        context=mp.get_context('spawn')
        self.jobs=context.Queue(maxsize=1);self.results=context.Queue(maxsize=8)
        self.process=context.Process(target=worker_loop,args=(self.jobs,self.results,int(ip['phys_addr']),int(ip['addr_range']),str(folder)),daemon=True)
        self.process.start();self.generation=0;self.channel=2;self.total=0;self.last_submit=0
        self.raw=np.empty(0,np.int32);self.events={};self.candidates=[];self.last_write=0
        self.status_file=Path(status_file);self.error=None
    def reset(self,ch):
        self.generation+=1;self.channel=ch;self.total=0;self.last_submit=0
        self.raw=np.empty(0,np.int32);self.events={};self.candidates=[]
    def update(self,block):
        self.total+=len(block)
        self.raw=np.concatenate([self.raw,block[:,self.channel-1]])[-12000:]
        while True:
            try:message=self.results.get_nowait()
            except queue.Empty:break
            if 'error' in message:
                if self.error!=message['error']:print('INFERENCE_ERROR',message['error'],flush=True)
                self.error=message['error'];continue
            if message['generation']!=self.generation:continue
            self.candidates=message['candidates']
            for beat in message['beats']:self.events[beat['source_sample']]=beat
        if not self.process.is_alive():self.error=self.error or 'Inference worker stopped'
        if len(self.raw)>=3000 and self.total-self.last_submit>=250 and not self.error:
            job=(self.generation,self.channel,self.total-len(self.raw),self.raw.copy())
            try:self.jobs.put_nowait(job);self.last_submit=self.total
            except queue.Full:pass
        if time.monotonic()-self.last_write>1:
            payload=dict(channel=self.channel,generation=self.generation,samples=self.total,
                         worker_alive=self.process.is_alive(),error=self.error,beats=list(self.events.values())[-64:])
            self.status_file.parent.mkdir(exist_ok=True,parents=True)
            tmp=self.status_file.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2));tmp.replace(self.status_file)
            self.last_write=time.monotonic()
        self.events={i:v for i,v in self.events.items() if i>self.total-30000}
    def plane(self):
        labels=np.zeros((2,2,640),np.uint32)
        anchors={i:'?' for i in self.candidates}
        anchors.update({i:e['label'] for i,e in self.events.items()})
        for anchor,label in anchors.items():
            for path,delay in enumerate([174,15]):
                column=int((anchor+delay-(self.total-2000))*640/2000)
                # 16-pixel glyphs are aligned with the RTL's doubled ASCII cells.
                column=(column//16)*16
                if 0<=column<640:labels[self.channel-1,path,column:min(column+16,640)]=ord(label)
        if self.error:
            for i,c in enumerate('ERROR'):labels[:,:,448+i*16:464+i*16]=ord(c)
        return labels.reshape(-1)
    def close(self):
        try:self.jobs.put_nowait(None)
        except queue.Full:pass
        self.process.join(timeout=4)
        if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)


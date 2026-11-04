"""Bounded, asynchronous, delayed beat recognition. No FPGA overlay reload in worker."""
import json,multiprocessing as mp,queue,time,os
import logging
from logging.handlers import RotatingFileHandler
from bisect import bisect_left
from pathlib import Path
import numpy as np
from label_layout import put_label
from monitoring import assess_quality,measure_monitor,MonitorState

def recognize_snapshot(model,accelerator,config,job,last_anchor):
    from ecg_model import preprocess,detect_beats,beat_input
    gen,ch,start,raw=job
    begin=time.monotonic();filtered=preprocess(raw.astype(float)*(2.42/6/(2**23-1)*1000))
    times=detect_beats(filtered);end_sample=start+len(raw)
    candidates=[int(start+round(t*500)) for t in times]
    emitted=[];rejected=[]
    for j in range(1,len(times)-1):
        anchor=int(start+round(times[j]*500))
        if anchor<=last_anchor+100 or times[j]>len(raw)/500-2.0:continue
        local=anchor-start
        quality=assess_quality(raw[max(0,local-1000):local+1000],filtered[max(0,round((local-1000)*256/500)):round((local+1000)*256/500)])
        if quality['state']!='GOOD':
            rejected.append(dict(source_sample=anchor,quality=quality));last_anchor=anchor;continue
        try:x,rr=beat_input(filtered,times,j,config)
        except ValueError:continue
        inference_start=time.monotonic();conv_start=accelerator.seconds;calls_start=accelerator.calls
        logits=model(x,rr);p=np.exp(logits-logits.max());p/=p.sum()
        emitted.append(dict(source_sample=anchor,channel=ch,label=config['classes'][int(p.argmax())],quality=quality,
            confidence=float(p.max()),probabilities=p.tolist(),inference_seconds=time.monotonic()-inference_start,
            fpga_conv_seconds=accelerator.seconds-conv_start,fpga_conv_calls=accelerator.calls-calls_start,
            available_through_sample=end_sample,buffer_wait_seconds=(end_sample-anchor)/500,
            processing_seconds=time.monotonic()-begin))
        last_anchor=anchor
    return dict(generation=gen,channel=ch,candidates=candidates,beats=emitted,rejected=rejected,
                monitor=measure_monitor(raw,filtered,times),available_through_sample=end_sample,
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
        self.monitor=MonitorState(json.loads((Path(folder).parent/'monitor_config.json').read_text()))
        self.instant_bad=False;self.rejected={};self.last_monitor_state=None
        self.classified_total=0;self.rejected_total=0
        self.log_file=Path('/var/log/ecg-scope/monitor.jsonl');self.log_file.parent.mkdir(parents=True,exist_ok=True)
        self.logger=logging.getLogger('ecg.monitor');self.logger.setLevel(logging.INFO);self.logger.propagate=False
        self.log_handler=RotatingFileHandler(self.log_file,maxBytes=2*1024*1024,backupCount=2)
        self.logger.addHandler(self.log_handler)
    def reset(self,ch):
        self.generation+=1;self.channel=ch;self.total=0;self.last_submit=0
        self.raw=np.empty(0,np.int32);self.events={};self.candidates=[]
        self.monitor.reset();self.instant_bad=False;self.rejected={};self.last_monitor_state=None
        self.classified_total=0;self.rejected_total=0
    def update(self,block):
        self.total+=len(block)
        self.raw=np.concatenate([self.raw,block[:,self.channel-1]])[-12000:]
        recent=self.raw[-500:]
        self.instant_bad=len(recent)>=500 and (np.ptp(recent.astype(float))*(2.42/6/(2**23-1)*1000)<.015 or np.mean(np.abs(recent.astype(float))>=.98*(2**23-1))>.001)
        if self.instant_bad:self.monitor.reset()
        while True:
            try:message=self.results.get_nowait()
            except queue.Empty:break
            if 'error' in message:
                if self.error!=message['error']:print('INFERENCE_ERROR',message['error'],flush=True)
                self.error=message['error'];continue
            if message['generation']!=self.generation:continue
            self.classified_total+=len(message['beats']);self.rejected_total+=len(message['rejected'])
            self.candidates=message['candidates']
            for beat in message['beats']:self.events[beat['source_sample']]=beat
            for item in message['rejected']:self.rejected[item['source_sample']]=item
            if not self.instant_bad:self.monitor.ingest(message['monitor'],message['available_through_sample']/500,message['beats'])
        if not self.process.is_alive():self.error=self.error or 'Inference worker stopped'
        if len(self.raw)>=3000 and self.total-self.last_submit>=250 and not self.error:
            job=(self.generation,self.channel,self.total-len(self.raw),self.raw.copy())
            try:self.jobs.put_nowait(job);self.last_submit=self.total
            except queue.Full:pass
        if time.monotonic()-self.last_write>1:
            monitor=self.current_monitor()
            payload=dict(pid=os.getpid(),channel=self.channel,generation=self.generation,samples=self.total,monitor=monitor,
                         classified_total=self.classified_total,rejected_total=self.rejected_total,
                         quality_metrics=self.monitor.measurement,
                         worker_alive=self.process.is_alive(),error=self.error,beats=list(self.events.values())[-64:])
            self.status_file.parent.mkdir(exist_ok=True,parents=True)
            tmp=self.status_file.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2));tmp.replace(self.status_file)
            self.last_write=time.monotonic()
            entry=dict(pid=os.getpid(),channel=self.channel,generation=self.generation,samples=self.total,monitor=monitor,
                       classified_total=self.classified_total,rejected_total=self.rejected_total,
                       event_transition=monitor['state']!=self.last_monitor_state,worker_alive=self.process.is_alive())
            self.logger.info(json.dumps(entry))
            self.last_monitor_state=monitor['state']
        self.events={i:v for i,v in self.events.items() if i>self.total-30000}
        self.rejected={i:v for i,v in self.rejected.items() if i>self.total-30000}
    def current_monitor(self):return self.monitor.view(self.total/500,self.error,self.instant_bad)
    def plane(self):
        labels=np.zeros((2,2,640),np.uint32)
        if getattr(self,'monitor',None) is not None and self.current_monitor()['quality']!='GOOD':return labels.reshape(-1)
        # A re-detected pending peak may move by one sample. Once classified,
        # retain its original anchor and avoid an overlapping '?' fragment.
        known=sorted(set(self.events)|set(getattr(self,'rejected',{})))
        anchors={}
        for i in self.candidates:
            j=bisect_left(known,i)
            if (j and i-known[j-1]<=100) or (j<len(known) and known[j]-i<=100):continue
            anchors[i]='?'
        anchors.update({i:e['label'] for i,e in self.events.items()})
        for anchor,label in anchors.items():
            for path,delay in enumerate([174,15]):
                column=int(np.floor((anchor+delay-(self.total-2000))*640/2000))
                put_label(labels[self.channel-1,path],column,label)
        if self.error:
            put_label(labels,448,'ERROR')
        return labels.reshape(-1)
    def close(self):
        try:self.jobs.put_nowait(None)
        except queue.Full:pass
        self.process.join(timeout=4)
        if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
        self.logger.removeHandler(self.log_handler);self.log_handler.close()


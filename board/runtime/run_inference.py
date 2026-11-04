"""Standalone ECG live display plus FPGA convolution and delayed beat labels."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import sys
import time
import json,traceback
import numpy as np
import scope_runtime
from stream_inference import StreamRecognizer
from label_layout import put_label
from hud import HUD
from session_capture import SessionCapture

def main():
    root=Path(__file__).resolve().parent
    active=[]
    hud=HUD(root);capture=SessionCapture(root)
    original_init=scope_runtime.ScopeIO.__init__
    original_drain=scope_runtime.ScopeIO.drain
    original_draw=scope_runtime.ScopeIO.draw
    original_switch=scope_runtime.ScopeIO.select_rld_channel
    original_adc_init=scope_runtime.ScopeIO.initialize_adc
    original_overlay=None
    replay='--source' in sys.argv and sys.argv[sys.argv.index('--source')+1]=='replay'
    # Hook Overlay construction once; the inference process attaches only to conv MMIO.
    import pynq
    original_overlay=pynq.Overlay
    def overlay_factory(*args,**kwargs):
        overlay=original_overlay(*args,**kwargs)
        active.append(StreamRecognizer(overlay,root/'model','/run/ecg-scope/inference_status.json'))
        return overlay
    def init(self,ip):original_init(self,ip)
    def initialize_adc(self,test_signal=False,rld_channel=1):
        result=original_adc_init(self,test_signal,rld_channel)
        active[0].reset(rld_channel)
        return result
    def drain(self,limit=64):
        block=original_drain(self,limit)
        if len(block):active[0].update(block);capture.feed(block)
        return block
    def switch(self,ch):
        original_switch(self,ch);active[0].reset(ch)
        self.last_history=None;self.last_plane=None
    def draw(self,history):
        if self.ip.read(0x1c)&4:return False
        held=bool(self.ip.read(0x10)&4)
        if not held or getattr(self,'last_history',None) is None:
            self.last_history=history
            self.last_plane=active[0].plane().reshape(2,2,640)
        plane=self.last_plane
        if replay:
            # Persistent, visible provenance on every channel and path.
            put_label(plane,544,'REPLAY')
        self.ip.mmio.array[0x7000//4:0x9800//4]=plane.reshape(-1)
        self.ip.mmio.array[0xa000//4:0xaa00//4]=hud.render(active[0].current_monitor())
        return original_draw(self,self.last_history)
    def report_error(self,message):
        state=dict(bpm=None,quality='ERROR',state='ACQUISITION_ERROR',reason=message)
        active[0].error=message;active[0].monitor.reset();active[0].events.clear()
        fault=dict(pid=os.getpid(),channel=active[0].channel,samples=active[0].total,monitor=state,error=message,beats=[],analysis_enabled=False)
        (root/'acquisition_fault.json').write_text(json.dumps(fault,indent=2))
        active[0].status_file.write_text(json.dumps(fault,indent=2))
        active[0].logger.error(json.dumps(fault))
        deadline=time.monotonic()+.15
        while self.ip.read(0x1c)&4 and time.monotonic()<deadline:time.sleep(.001)
        if self.ip.read(0x1c)&4:return
        self.ip.mmio.array[0x7000//4:0x9800//4]=0
        self.ip.mmio.array[0xa000//4:0xaa00//4]=hud.render(state)
        original_draw(self,np.zeros((2000,2,2),np.int32))
        while self.ip.read(0x1c)&4 and time.monotonic()<deadline:time.sleep(.001)
    def feed_replay(self,raw,reset):
        ch=(self.ip.read(0x10)&1)+1
        if reset or active[0].channel!=ch:active[0].reset(ch)
        if raw is not None:active[0].update(raw)
    pynq.Overlay=overlay_factory
    scope_runtime.ScopeIO.__init__=init;scope_runtime.ScopeIO.drain=drain
    scope_runtime.ScopeIO.initialize_adc=initialize_adc
    scope_runtime.ScopeIO.draw=draw;scope_runtime.ScopeIO.select_rld_channel=switch
    scope_runtime.ScopeIO.feed_replay=feed_replay
    scope_runtime.ScopeIO.report_error=report_error
    exit_code=0
    try:scope_runtime.main()
    except Exception as exc:
        traceback.print_exc()
        traceback.clear_frames(exc.__traceback__)
        exit_code=1
    finally:
        pynq.Overlay=original_overlay
        for recognizer in active:recognizer.close()
        capture.close()
    return exit_code

if __name__=='__main__':sys.exit(main())

"""Standalone ECG live display plus FPGA convolution and delayed beat labels."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import sys
import scope_runtime
from stream_inference import StreamRecognizer

def main():
    root=Path(__file__).resolve().parent
    active=[]
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
        if len(block):active[0].update(block)
        return block
    def switch(self,ch):
        original_switch(self,ch);active[0].reset(ch)
    def draw(self,history):
        if self.ip.read(0x10)&4 or self.ip.read(0x1c)&4:return False
        plane=active[0].plane().reshape(2,2,640)
        if replay:
            # Persistent, visible provenance on every channel and path.
            for i,c in enumerate('REPLAY'):
                plane[:,:,544+i*16:560+i*16]=ord(c)
        self.ip.mmio.array[0x7000//4:0x9800//4]=plane.reshape(-1)
        return original_draw(self,history)
    def feed_replay(self,raw,reset):
        ch=(self.ip.read(0x10)&1)+1
        if reset or active[0].channel!=ch:active[0].reset(ch)
        if raw is not None:active[0].update(raw)
    pynq.Overlay=overlay_factory
    scope_runtime.ScopeIO.__init__=init;scope_runtime.ScopeIO.drain=drain
    scope_runtime.ScopeIO.initialize_adc=initialize_adc
    scope_runtime.ScopeIO.draw=draw;scope_runtime.ScopeIO.select_rld_channel=switch
    scope_runtime.ScopeIO.feed_replay=feed_replay
    try:scope_runtime.main()
    finally:
        pynq.Overlay=original_overlay
        for recognizer in active:recognizer.close()

if __name__=='__main__':main()

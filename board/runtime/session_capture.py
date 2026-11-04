"""Consume an explicit one-shot capture request for integration-test evidence."""
import json
from pathlib import Path
import numpy as np

class SessionCapture:
    def __init__(self,folder):
        self.file=None;self.samples=0;self.limit=0;self.folder=Path(folder)
        request=self.folder/'capture_request.json'
        if request.exists():
            seconds=float(json.loads(request.read_text())['seconds'])
            if not 0<seconds<=600:raise ValueError('Capture duration outside 0..600 s')
            request.replace(self.folder/'capture_request.consumed.json')
            self.limit=round(seconds*500)
            self.file=(self.folder/'validation_live.raw').open('wb',buffering=65536)
    def feed(self,block):
        if self.file is None:return
        data=np.asarray(block[:self.limit-self.samples],dtype='<i4')
        self.file.write(data.tobytes());self.samples+=len(data)
        if self.samples>=self.limit:self.close()
    def close(self):
        if self.file is None:return
        self.file.close();self.file=None
        raw=np.fromfile(self.folder/'validation_live.raw',dtype='<i4').reshape(-1,2)
        np.save(self.folder/'validation_live.npy',raw)
        (self.folder/'validation_live.json').write_text(json.dumps(dict(samples_per_channel=len(raw),nominal_sps=500,channels=2,
            requested_samples=self.limit,complete=self.samples>=self.limit,source='live ADS1292 raw; CN2 electrodes; CH1 not connected to electrodes'),indent=2))

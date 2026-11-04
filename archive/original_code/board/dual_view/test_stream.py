"""Replay causally arriving raw samples through the deployment window scheduler."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from ecg_model import BeatModel
from stream_inference import recognize_snapshot,StreamRecognizer

root=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent/'model'
model=BeatModel(folder);config=json.loads((folder/'config.json').read_text())
reference=json.loads((folder/'reference_results.json').read_text())
records=root/'模型训练/采集/2026-11-04_真实心电_已保存记录/01_板端原始文件'
summary=[]
for name,ch in [('electrode_cn2_20261104',2),('electrode_cn4_rld1_20261104',1)]:
    raw=np.load(records/name/'raw.npy')[:,ch-1]
    last=-1e9;events=[]
    for end in list(range(3000,len(raw),250))+[len(raw)]:
        start=max(0,end-12000)
        message,last=recognize_snapshot(model,SimpleNamespace(seconds=0,calls=0),config,
                                         (1,ch,start,raw[start:end]),last)
        events.extend(message['beats'])
    assert events and all(e['buffer_wait_seconds']>=2 for e in events)
    assert all(a['source_sample']<b['source_sample']-100 for a,b in zip(events,events[1:]))
    baseline=[e for e in reference['records'] if e['recording']==name]
    matches=[]
    for e in events:
        nearest=min(baseline,key=lambda b:abs(b['anchor_nominal_s']*500-e['source_sample']))
        assert abs(nearest['anchor_nominal_s']*500-e['source_sample'])<20
        matches.append(e['label']==nearest['label'])
    # Verify visible labels belong to the selected channel and remain inside the frame.
    display=StreamRecognizer.__new__(StreamRecognizer)
    display.total=len(raw);display.channel=ch;display.candidates=[]
    display.events={e['source_sample']:e for e in events};display.error=None
    plane=display.plane().reshape(2,2,640)
    assert not plane[2-ch].any() and plane[ch-1].any()
    summary.append(dict(recording=name,beats=len(events),whole_record_class_matches=sum(matches),
        min_buffer_wait_seconds=min(e['buffer_wait_seconds'] for e in events),events=events))
result=dict(passed=True,records=summary,note='Desktop streaming test; finite-context filtering can differ from whole-record filtering; no diagnostic ground truth')
(folder/'stream_host_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps({**result,'records':[{k:v for k,v in r.items() if k!='events'} for r in summary]},indent=2))

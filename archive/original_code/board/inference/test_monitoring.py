import json
from pathlib import Path
import numpy as np
from monitoring import assess_quality,measure_monitor,MonitorState,MV_PER_CODE
from ecg_model import preprocess,detect_beats
from hud import HUD
from session_capture import SessionCapture

root=Path(__file__).resolve().parents[2];folder=Path(__file__).parent
config=json.loads((folder/'monitor_config.json').read_text())
good=lambda bpm:dict(quality=dict(state='GOOD',reason='GOOD'),bpm=bpm)
beat=lambda i,label='V',p=.99:dict(source_sample=i*500,label=label,confidence=p,quality=dict(state='GOOD'))
m=MonitorState(config)
for t in range(12):m.ingest(good(150),t,[])
assert m.view(11)['state']=='OBSERVE'
m.ingest(good(150),12,[]);assert m.view(12)['state']=='RATE_HIGH'
for t in range(13,28):m.ingest(good(75),t,[])
assert m.view(27)['state']=='OBSERVE'
assert m.view(32)['bpm'] is None and m.view(32)['state']=='STALE'
m.ingest(good(150),50,[])
assert m.view(50)['bpm'] is None # A stale gap cannot count toward sustained alerts.
m.reset()
for t in range(5):m.ingest(good(75),t,[beat(t)])
assert m.view(4)['state']=='MODEL_REVIEW'
m.ingest(dict(quality=dict(state='POOR',reason='MAINS'),bpm=75),5,[])
assert m.view(5)['bpm'] is None and m.view(5)['state']=='SIGNAL_BAD'
for label,p in [('V',.6),('|',.99),('N',.99)]:
    m.reset()
    for t in range(12):m.ingest(good(75),t,[beat(t,label,p)])
    assert m.view(11)['state']=='OBSERVE'
m.reset()
for t in range(8):m.ingest(good(75),t,[beat(1)])
assert m.view(7)['state']=='OBSERVE' # Repeated messages are not new beats.
assert assess_quality(np.zeros(2000),np.zeros(1024))['state']=='POOR'
assert assess_quality(np.full(2000,8388607),np.ones(1024))['reason']=='CLIPPED'
t=np.arange(6000)/500
ecg=sum(np.exp(-.5*((t-k)/.016)**2) for k in range(1,12))+.02*np.sin(2*np.pi*.2*t)
raw=np.rint(ecg/MV_PER_CODE).astype(np.int32)
y=preprocess(raw*MV_PER_CODE);peaks=detect_beats(y);measured=measure_monitor(raw,y,peaks)
assert measured['quality']['state']=='GOOD' and abs(measured['bpm']-60)<1,measured
noise=np.rint(np.sin(2*np.pi*50*t)/MV_PER_CODE).astype(np.int32)
assert assess_quality(noise[-2000:],preprocess(noise*MV_PER_CODE)[-1024:])['state']=='POOR'
results=[]
records=root/'模型训练/采集/2026-11-04_真实心电_已保存记录/01_板端原始文件'
for name,ch,lo,hi in [('electrode_cn2_20261104',1,2250,7250),('electrode_cn4_rld1_20261104',0,1000,6000)]:
    raw=np.load(records/name/'raw.npy')[:,ch]
    selected=raw[lo:hi];y=preprocess(selected*MV_PER_CODE)
    result=measure_monitor(selected,y,detect_beats(y))
    assert result['quality']['state']=='GOOD' and result['bpm'] is not None,result
    results.append(dict(recording=name,measurement=result))
hud=HUD(folder)
for quality,state in [('GOOD','OBSERVE'),('POOR','SIGNAL_BAD'),('WARMUP','WARMUP'),('STALE','STALE'),('ERROR','ACQUISITION_ERROR')]:
    image=hud.render(dict(bpm=75 if quality=='GOOD' else None,quality=quality,state=state))
    assert image.shape==(640,) and image.max()<2**18 and (image&65535).any()
capture_folder=root/'build/monitor_capture_test';capture_folder.mkdir(exist_ok=True)
(capture_folder/'capture_request.json').write_text('{"seconds":0.01}')
capture=SessionCapture(capture_folder);block=np.arange(16,dtype=np.int32).reshape(8,2)
capture.feed(block[:3]);capture.feed(block[3:])
assert np.array_equal(np.load(capture_folder/'validation_live.npy'),block[:5])
assert json.loads((capture_folder/'validation_live.json').read_text())['complete']
(root/'report/monitor_host_tests_20261104.json').write_text(json.dumps(dict(passed=True,records=results),indent=2))
print('MONITOR_TESTS_PASS',json.dumps(results))

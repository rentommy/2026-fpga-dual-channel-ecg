"""Restore a verified board evidence bundle and make the integration report plot."""
import argparse,base64,csv,hashlib,io,json,os,shutil,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from ecg_model import preprocess,detect_beats
from monitoring import MV_PER_CODE

p=argparse.ArgumentParser();p.add_argument('png',type=Path);p.add_argument('--sha256',required=True);args=p.parse_args()
root=Path(__file__).resolve().parents[2];out=root/'report/monitoring_20261104';out.mkdir(exist_ok=True)
im=Image.open(args.png);payload=base64.b64decode(im.info['evidence_zip_base64'])
assert hashlib.sha256(payload).hexdigest()==im.info['evidence_zip_sha256']==args.sha256
(out/'board_evidence.zip').write_bytes(payload)
with zipfile.ZipFile(io.BytesIO(payload)) as z:z.extractall(out)
shutil.copyfile(args.png,out/'board_verification.png')
raw=np.load(out/'validation_live.npy',allow_pickle=False)
meta=json.loads((out/'validation_live.json').read_text());assert meta['complete'] and raw.shape==(90000,2)
baseline=json.loads((out/'baseline_runtime.json').read_text())
pid=baseline['display']['pid']
rows=[json.loads(line) for line in (out/'monitor.jsonl').read_text().splitlines() if line.strip()]
rows=[r for r in rows if r['pid']==pid and r['samples']<=90000 and 'classified_total' in r]
summary=dict(complete=True,samples_per_channel=len(raw),nominal_seconds=len(raw)/500,
             source='live ADS1292 CN2',baseline=baseline,
             monitor_records=len(rows),valid_hr_records=sum(r['monitor']['bpm'] is not None for r in rows),
             quality_states=sorted(set(r['monitor']['quality'] for r in rows)),
             hr_min=min(r['monitor']['bpm'] for r in rows if r['monitor']['bpm'] is not None),
             hr_max=max(r['monitor']['bpm'] for r in rows if r['monitor']['bpm'] is not None),
             note='Engineering integration test; no clinical annotation or reference pulse device; power-cycle test reserved for user')
(out/'summary.json').write_text(json.dumps(summary,indent=2))
with (out/'heart_rate_quality.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f);w.writerow(['sample','nominal_seconds','heart_rate_bpm','quality','state','classified_total','rejected_total'])
    for r in rows:w.writerow([r['samples'],r['samples']/500,r['monitor']['bpm'],r['monitor']['quality'],r['monitor']['state'],r['classified_total'],r['rejected_total']])
os.environ.setdefault('MPLCONFIGDIR',str(root/'build/matplotlib'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei'];plt.rcParams['axes.unicode_minus']=False
fig,ax=plt.subplots(2,1,figsize=(12,6),constrained_layout=True)
y=preprocess(raw[:,1]*MV_PER_CODE);peaks=detect_beats(y)
start=30;end=40;t=np.arange(len(y))/256
mask=(t>=start)&(t<end)
ax[0].plot(t[mask],y[mask],linewidth=.8,color='#087f8c')
shown=peaks[(peaks>=start)&(peaks<end)]
ax[0].scatter(shown,y[np.rint(shown*256).astype(int)],s=16,color='#ca7630',label='自动定位的R峰')
ax[0].set(xlabel='采集时间（秒）',ylabel='滤波幅度（mV）',title='CN2 实时采集片段（通道2）');ax[0].legend();ax[0].grid(alpha=.2)
ax[1].plot([r['samples']/500 for r in rows],[np.nan if r['monitor']['bpm'] is None else r['monitor']['bpm'] for r in rows],color='#287a3b')
bad=[r for r in rows if r['monitor']['quality'] not in ['GOOD','WARMUP']]
for r in bad:ax[1].axvline(r['samples']/500,color='#d39b30',alpha=.15,linewidth=2)
ax[1].set(xlabel='采集时间（秒）',ylabel='显示心率（次/分）',title='三分钟实时心率与质量门控（无效状态不显示心率）',xlim=(0,180));ax[1].grid(alpha=.2)
fig.suptitle('采集 → FPGA滤波/卷积 → ARM心率/质量/预警 → HDMI：工程闭环验证')
fig.savefig(out/'live_monitor_overview.png',dpi=150);plt.close(fig)
dest=root/'模型训练/采集/2026-11-04_实时监测闭环测试';dest.mkdir(exist_ok=True)
for name in ['validation_live.npy','validation_live.json','heart_rate_quality.csv','summary.json','live_monitor_overview.png']:
    shutil.copyfile(out/name,dest/name)
print(json.dumps({k:v for k,v in summary.items() if k!='baseline'},ensure_ascii=False,indent=2))

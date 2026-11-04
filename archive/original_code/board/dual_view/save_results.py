"""Verify the board's exported result bundle, then write a per-beat CSV and plot."""
import argparse,base64,csv,hashlib,io,json,shutil,zipfile,os
from pathlib import Path
from PIL import Image
import numpy as np
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[2]/'build/matplotlib'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

p=argparse.ArgumentParser();p.add_argument('png',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parents[2];folder=root/'report/inference_20261104';folder.mkdir(exist_ok=True)
im=Image.open(args.png);payload=base64.b64decode(im.info['results_zip_base64'])
assert hashlib.sha256(payload).hexdigest()==im.info['results_zip_sha256']=='bffe0f15f9fe858b6b772f5032845df9b2bd381034a2fe718c87da1e75789684'
(folder/'board_results.zip').write_bytes(payload)
with zipfile.ZipFile(io.BytesIO(payload)) as z:z.extractall(folder)
shutil.copyfile(args.png,folder/'hardware_verification.png')
for field,name in [('channel1_runtime_json','channel1_runtime.json'),('latest_runtime_json','latest_runtime.json')]:
    if field in im.info:
        json.loads(im.info[field])
        (folder/name).write_text(im.info[field])
results=json.loads((folder/'fpga_replay_results.json').read_text())
assert results['passed'] and len(results['results'])==49
fields=list(results['results'][0])
with (folder/'per_beat_fpga_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results['results'])
selected=[]
for beat in results['results']:
    lo,hi=(4.5,14.5) if beat['recording']=='electrode_cn2_20261104' else (2,12)
    if lo+.301<=beat['anchor_nominal_s']<=hi-.496:selected.append(beat)
with (folder/'selected_segment_fpga_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(selected)
plt.rcParams['font.sans-serif']=['Microsoft YaHei'];plt.rcParams['axes.unicode_minus']=False
fig,axes=plt.subplots(2,1,figsize=(13,7.5),constrained_layout=True)
for ax,name,ch in zip(axes,['electrode_cn2_20261104','electrode_cn4_rld1_20261104'],[2,1]):
    y=np.load(root/'board/inference/model'/(name+'_filtered256.npy'));t=np.arange(len(y))/256
    ax.plot(t,y,color='#087f8c',linewidth=.8)
    lo,hi=(4.5,14.5) if ch==2 else (2,12)
    ax.axvspan(lo,hi,color='#96d6b4',alpha=.16,label='此前优选的10秒区间')
    for beat in results['results']:
        if beat['recording']!=name:continue
        x=beat['anchor_nominal_s'];label=beat['label']
        ax.axvline(x,color='#b9c2c7',linewidth=.45,alpha=.5)
        ax.text(x,1.02,label,ha='center',va='bottom',transform=ax.get_xaxis_transform(),
                color='#287a3b' if label=='N' else '#b14d16',fontsize=10)
    ax.set(xlabel='记录时间（秒）',ylabel='滤波幅度（mV）',xlim=(0,len(y)/256))
    ax.set_title(f'通道{ch}：'+('CN2 记录' if ch==2 else 'CN4 记录')+'（两次独立采集）',loc='left',pad=30,fontsize=11)
    ax.grid(alpha=.2)
    ax.legend(loc='lower left',fontsize=8)
fig.suptitle('自行采集 ECG 的 FPGA 部署验证：49/49 分类一致；无专家标注，不能作为诊断结论',fontsize=12)
fig.savefig(folder/'classified_ecg.png',dpi=160);plt.close(fig)
dest=root/'模型训练/采集/2026-11-04_真实心电_已保存记录/04_FPGA识别测试';dest.mkdir(exist_ok=True)
for name in ['fpga_replay_results.json','per_beat_fpga_results.csv','selected_segment_fpga_results.csv','classified_ecg.png']:
    shutil.copyfile(folder/name,dest/name)
print(json.dumps({k:v for k,v in results.items() if k!='results'},indent=2))
print('SAVED',folder)
print('SELECTED_SEGMENT_BEATS',len(selected))

"""Package the verified overlay, model and explicitly identified real-record replay."""
import argparse,hashlib,json,zipfile
from pathlib import Path
import numpy as np

here=Path(__file__).resolve().parent;root=here.parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--name',default='ecg_inference_20261104');args=parser.parse_args()
if not args.name.replace('_','').isalnum():raise ValueError('Invalid package name')
records=root/'模型训练/采集/2026-11-04_真实心电_已保存记录/01_板端原始文件'
a=np.load(records/'electrode_cn4_rld1_20261104/raw.npy')[:,0]
b=np.load(records/'electrode_cn2_20261104/raw.npy')[:,1]
n=min(len(a),len(b))
np.save(here/'model/replay_raw.npy',np.column_stack([a[:n],b[:n]]).astype(np.int32))
(here/'model/replay_provenance.json').write_text(json.dumps(dict(
    sample_rate=500,samples=n,channel1='electrode_cn4_rld1_20261104/raw.npy[:,0]',
    channel2='electrode_cn2_20261104/raw.npy[:,1]',
    simultaneous=False,note='Two separate recordings from the same person; displayed together only for deployment replay. Not a simultaneous two-lead recording.'),indent=2))
files=[here/n for n in ['ecg_model.py','label_layout.py','monitoring.py','monitor_config.json','hud.py','hud_glyphs.npz','session_capture.py','stream_inference.py','scope_runtime.py','run_inference.py',
                        'verify_fpga.py','install.py','GUIDE.md']]
files+=list((here/'model').glob('*'))
files+=[here/'overlay/ecg_inference.bit',here/'overlay/ecg_inference.hwh']
assert all(p.is_file() for p in files)
manifest={str(p.relative_to(here)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(here/'manifest.json').write_text(json.dumps(manifest,indent=2))
archive=root/'board'/(args.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files+[here/'manifest.json']:z.write(p,args.name+'/'+str(p.relative_to(here)).replace('\\','/'))
print(archive,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())

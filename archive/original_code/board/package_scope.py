"""Package the verified scope overlay without any obsolete overlay files."""
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parent.parent
out=root/'board/scope'
manifest={'date':'2026-10-23','target':'PYNQ-Z2 xc7z020clg400-1','vivado':'2026.1',
 'timing':{'setup_slack_ns':0.041,'hold_slack_ns':0.023,'core_mhz':100,'pixel_mhz':25.2,'serial_mhz':126},
 'resources':{'lut':6751,'ff':9665,'dsp':1,'bram_tiles':17},
 'validation':{'rtl_io':'PASS','rtl_video':'PASS','board':'pending',
 'physical_hdmi':'not tested: no monitor','physical_adc':'not tested: isolation HOST side not designed',
 'external_gpio_timing':'requires final isolator specifications and electrical validation'},'sha256':{}}
result=out/'board_acceptance.json'
if result.exists():manifest['validation']['board']=json.loads(result.read_text())
files=[root/'board/run_scope.py',root/'board/verify_overlay.py',root/'board/SCOPE_GUIDE.md',
 root/'board/ads1292_pmoda.xdc',root/'board/ads1292_pinmap.json',root/'board/scope_hdmi.xdc',
 root/'data/input_raw.txt',root/'data/golden_float.txt']
files+=list(out.glob('*.bit'))+list(out.glob('*.hwh'))+list(out.glob('*.rpt'))+list(out.glob('*.png'))+list(out.glob('*.json'))
files=[p for p in files if p.name!='build_manifest.json']
for p in files:manifest['sha256'][p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(out/'build_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
files.append(out/'build_manifest.json')
def cell(kind,text):return dict(cell_type=kind,metadata={},source=text.splitlines(True),**({'execution_count':None,'outputs':[]} if kind=='code' else {}))
setup="""from pathlib import Path
import zipfile, hashlib, json
root=Path('ecg_scope_20261023')
with zipfile.ZipFile('ecg_scope_20261023.zip') as z:z.extractall(root)
m=json.loads((root/'board/scope/build_manifest.json').read_text())
for p in ['board/scope/ecg_scope.bit','board/scope/ecg_scope.hwh']:
    assert hashlib.sha256((root/p).read_bytes()).hexdigest()==m['sha256'][p]
print('SCOPE_PACKAGE_HASH_PASS')
"""
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':[
cell('markdown','# ECG HDMI / Pmod A\n默认演示数据，不启动 ADC。无显示器时不能验证实体画面。'),cell('code',setup),
cell('code','%run ecg_scope_20261023/board/verify_overlay.py --overlay ecg_scope_20261023/board/scope/ecg_scope.bit --output ecg_scope_20261023/board/scope/filter_board_output.npy'),
cell('code',"""from pynq import Overlay
ol=Overlay(str(root/'board/scope/ecg_scope.bit'),download=False)
io=ol.ecg_io
assert io.read(0x3c)==0x45434731
for v in range(8):
    io.write(0x14,v)
    assert io.read(0x10)&7==v
io.write(0x14,0)
print('SCOPE_AXI_UI_PASS', 'HPD',io.read(0x38))
"""),
cell('code','%run ecg_scope_20261023/board/run_scope.py --source demo --duration 8 --summary ecg_scope_20261023/board/scope/board_demo_summary.json'),
cell('code',"""f=json.loads((root/'board/scope/filter_board_output.json').read_text())
d=json.loads((root/'board/scope/board_demo_summary.json').read_text())
assert f['passed'] and d['error'] is None and d['samples_per_channel']>=3500
assert d['overruns']==0 and d['bad_frames']==0
accept={'filter':f,'demo':d,'axi_ui':'PASS','physical_hdmi':'NOT TESTED','physical_adc':'NOT TESTED'}
(root/'board/scope/board_acceptance.json').write_text(json.dumps(accept,indent=2))
print('SCOPE_BOARD_ACCEPTANCE_PASS')
print(json.dumps(accept,indent=2))
""") ]}
(root/'board/ECG_Scope_Start_20261023.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
with zipfile.ZipFile(root/'board/ecg_scope_20261023.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,p.relative_to(root).as_posix())
print('PACKAGE_READY',hashlib.sha256((root/'board/ecg_scope_20261023.zip').read_bytes()).hexdigest())

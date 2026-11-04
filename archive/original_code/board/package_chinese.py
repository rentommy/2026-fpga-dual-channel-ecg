"""Package the Chinese HDMI revision with its routed timing measurements."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

root = Path(__file__).resolve().parents[1]
outdir = root / 'board/scope'
timing_text = (outdir/'timing_summary.rpt').read_text()
assert 'All user specified timing constraints are met.' in timing_text
timing_line = next(line.split() for line in timing_text.splitlines()
                   if re.match(r'^\s*-?\d+\.\d+\s+-?\d+\.\d+\s+\d+\s+\d+\s+-?\d+\.\d+', line))
usage = (outdir/'utilization.rpt').read_text()
def resource(label):
    return float(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*([\d,.]+)',usage).group(1).replace(',',''))

files = ['board/run_scope.py','board/SCOPE_GUIDE.md','board/scope_hdmi.xdc',
         'src/rtl/ecg_wave_video.sv','src/rtl/ecg_chinese_font.vh','src/rtl/ecg_chinese_labels.vh',
         'board/generate_chinese_font.py',
         'board/scope/ecg_scope.bit','board/scope/ecg_scope.hwh',
         'board/scope/timing_summary.rpt','board/scope/utilization.rpt',
         'board/scope/drc.rpt','board/scope/cdc.rpt',
         'board/scope/chinese_rtl_demo.png','board/scope/chinese_rtl_channel2.png']
manifest = {
    'date':'2026-11-03','target':'PYNQ-Z2 xc7z020clg400-1','vivado':'2026.1',
    'register_abi':'0x45434732','language':'zh-CN','glyphs':52,'glyph_size':'16x16',
    'display':{'double_buffer':True,'default_updates_hz':25,'tested_run_target_hz':30,'scan_hz':60,
               'flags':{'0':'采集信号','1':'演示波形','2':'无采集数据','3':'内部测试信号'}},
    'timing':{'setup_slack_ns':float(timing_line[0]),'hold_slack_ns':float(timing_line[4])},
    'resources':{'lut':resource('Slice LUTs'),'ff':resource('Slice Registers'),
                 'dsp':resource('DSPs'),'bram_tiles':resource('Block RAM Tile')},
    'validation':{'rtl_video':'PASS','host_display_protocol':'3 tests PASS',
                   'hardware_chinese_display':'pending at packaging'},
    'sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files},
}
(outdir/'chinese_manifest_20261103.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(outdir/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
out = root/'board/ecg_scope_chinese_20261103.zip'
with zipfile.ZipFile(root/'board/ecg_scope_20261023.zip') as old, zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name in old.namelist():
        if name not in files and name!='board/scope/build_manifest.json':
            z.writestr(name,old.read(name))
    for name in files:
        z.write(root/name,name)
    z.writestr('board/scope/build_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'path':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
                  'timing':manifest['timing'],'resources':manifest['resources']},ensure_ascii=False,indent=2))

"""Create a new release without modifying the historical 20261023 archive."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parents[1]
files = [
    'board/run_scope.py', 'board/SCOPE_GUIDE.md', 'board/scope_hdmi.xdc',
    'board/scope/ecg_scope.bit', 'board/scope/ecg_scope.hwh',
    'board/scope/timing_summary.rpt', 'board/scope/utilization.rpt',
    'board/scope/drc.rpt', 'board/scope/cdc.rpt',
]
manifest = {
    'date': '2026-11-03', 'target': 'PYNQ-Z2 xc7z020clg400-1',
    'vivado': '2026.1', 'register_abi': '0x45434732',
    'display': {'double_buffer': True, 'switch_at': 'hx=0, vy=480', 'target_updates_hz': 25, 'scan_hz': 60},
    'timing': {'setup_slack_ns': .001, 'hold_slack_ns': .023, 'core_mhz': 100, 'pixel_mhz': 25.2},
    'resources': {'lut': 6762, 'ff': 9676, 'dsp': 1, 'bram_tiles': 19.5},
    'validation': {'rtl_video': 'PASS', 'rtl_spi_fifo_axi_buttons': 'PASS',
                   'host_display_protocol': '3 tests PASS',
                   'hardware_doublebuffer': {'adc_test_samples': 6885, 'display_updates': 317,
                                            'display_measured_fps': 24.979562121471467,
                                            'overruns': 0, 'bad_frames': 0, 'swap_ack': 'PASS'},
                   'physical_tearing_feedback': 'pending at packaging'},
    'sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files},
}
out = root / 'board/ecg_scope_doublebuffer_20261103_r2.zip'
manifest_path = root / 'board/scope/doublebuffer_manifest_20261103.json'
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
with zipfile.ZipFile(root / 'board/ecg_scope_20261023.zip') as old, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as new:
    for name in old.namelist():
        if name not in files and name != 'board/scope/build_manifest.json':
            new.writestr(name, old.read(name))
    for name in files:
        new.write(root / name, name)
    new.writestr('board/scope/build_manifest.json', json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'path': str(out), 'bytes': out.stat().st_size,
                  'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}, indent=2))

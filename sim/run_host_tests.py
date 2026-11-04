"""Dependency-light release checks; does not require a board or change fixtures."""
import ast,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
for p in r.rglob('*.py'):
 if not any(x in p.parts for x in ['vendor','training_snapshot','archive']):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
for script,args in [('skill/report_gate.py',['--selftest']),('skill/overlay_check.py',['--selftest']),('sim/collect_hls_report.py',['--selftest']),('skill/report_gate.py',['build/reports/timing_summary.rpt'])]:
 subprocess.run([sys.executable,script,*args],cwd=r,check=True)
print('HOST_RELEASE_CHECKS_PASS')

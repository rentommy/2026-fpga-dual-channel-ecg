"""Generic Vivado timing/resource gate; no ECG-specific knowledge."""
import argparse,json,re
from pathlib import Path

def parse(text):
 lines=text.splitlines()
 for i,line in enumerate(lines):
  if 'WNS(ns)' in line and 'WHS(ns)' in line:
   for row in lines[i+1:i+7]:
    fields=row.split()
    if len(fields)>=8:
     try:
      wns,tns=float(fields[0]),float(fields[1]);setup_fail=int(fields[2]);whs,ths=float(fields[4]),float(fields[5]);hold_fail=int(fields[6])
     except ValueError:continue
     return dict(wns_ns=wns,whs_ns=whs,setup_failing_endpoints=setup_fail,hold_failing_endpoints=hold_fail,passed=wns>=0 and whs>=0 and setup_fail==0 and hold_fail==0)
 raise ValueError('Vivado timing summary table not found; do not infer a pass')

def main():
 p=argparse.ArgumentParser();p.add_argument('timing',nargs='?');p.add_argument('--output');p.add_argument('--selftest',action='store_true');a=p.parse_args()
 if a.selftest:
  h='WNS(ns) TNS(ns) setupfail setuptotal WHS(ns) THS(ns) holdfail holdtotal\n---\n'
  assert parse(h+'0.016 0 0 60000 0.002 0 0 60000')['passed']
  assert not parse(h+'-0.1 -0.1 1 60000 0.002 0 0 60000')['passed']
  assert not parse(h+'0.1 0 0 60000 -0.002 -0.002 1 60000')['passed']
  try:parse('empty')
  except ValueError:pass
  else:raise AssertionError('Missing evidence accepted')
  print('REPORT_GATE_SELFTEST_PASS');return
 if not a.timing:p.error('timing report required')
 result=parse(Path(a.timing).read_text(encoding='utf8'));print(json.dumps(result,indent=2))
 if a.output:Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf8')
 raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()

"""Read-only PYNQ overlay ABI validation, reusable across register-mapped IPs."""
import argparse,json

def check(ip,offset,expected):
 actual=int(ip.read(offset))
 if actual!=expected:raise RuntimeError(f'ABI mismatch: got {actual:#x}, expected {expected:#x}')
 return {'actual':hex(actual),'passed':True}

def main():
 p=argparse.ArgumentParser();p.add_argument('--overlay');p.add_argument('--ip');p.add_argument('--offset',type=lambda x:int(x,0),default=0x3c);p.add_argument('--expected',type=lambda x:int(x,0));p.add_argument('--selftest',action='store_true');a=p.parse_args()
 if a.selftest:
  class IP:
   def read(self,offset):return 0x1234
  assert check(IP(),0,0x1234)['passed']
  try:check(IP(),0,0x5678)
  except RuntimeError:pass
  else:raise AssertionError('Wrong ABI accepted')
  print('OVERLAY_CHECK_SELFTEST_PASS');return
 if not a.overlay or not a.ip or a.expected is None:p.error('--overlay --ip --expected required')
 from pynq import Overlay
 # Never reprogram PL or claim ownership of the running acquisition process.
 ol=Overlay(a.overlay,download=False)
 print(json.dumps(check(getattr(ol,a.ip),a.offset,a.expected)))
if __name__=='__main__':main()

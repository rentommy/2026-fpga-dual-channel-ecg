"""Read-only audit of a public release candidate; excludes generated/private dirs."""
from pathlib import Path
import re,json,hashlib,argparse,ast
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'__pycache__','.git','.venv','hls_ecg2','hls_conv'}
def files():
 for p in ROOT.rglob('*'):
  if not p.is_file():continue
  rel=p.relative_to(ROOT)
  if any(x in EXCLUDE for x in rel.parts):continue
  if str(rel).replace('\\','/').startswith(('build/vivado/','build/host/','build/rtl/','board/vendor/digilent/','board/board_files/','data/private/')):continue
  yield p
def main():
 p=argparse.ArgumentParser();p.add_argument('--output');a=p.parse_args();issues=[];items=[]
 for f in files():
  rel=f.relative_to(ROOT).as_posix()
  for part in f.relative_to(ROOT).parts:
   if part not in ['README.md','LICENSE'] and not re.fullmatch('[a-z0-9_.-]+',part):issues.append({'path':rel,'issue':'non_english_or_non_lowercase_name'});break
  if f.stat().st_size>=95*1024**2:issues.append({'path':rel,'issue':'oversize_for_normal_git'})
  if f.suffix in ['.py','.tcl','.ps1','.md','.txt','.json','.yml']:
   text=f.read_text(encoding='utf-8-sig',errors='replace')
   if re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',text):issues.append({'path':rel,'issue':'private_key'})
   if re.search(r'(?i)(?:password|api_key|access_token)\s*=\s*[\"\'][^\"\']+[\"\']',text):issues.append({'path':rel,'issue':'credential_literal_review'})
   if f.suffix=='.py' and not rel.startswith('archive/'):
    try:ast.parse(text)
    except SyntaxError as e:issues.append({'path':rel,'issue':'python_syntax','line':e.lineno})
  items.append({'path':rel,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
 result={'passed':not issues,'files':len(items),'total_bytes':sum(x['bytes'] for x in items),'issues':issues,'scope':'Filename, size, obvious credential literals and Python syntax only; not full reproducibility, legal clearance or clinical validation'}
 print(json.dumps(result,indent=2))
 if a.output:Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf8')
 raise SystemExit(0 if not issues else 1)
if __name__=='__main__':main()

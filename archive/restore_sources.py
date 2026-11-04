"""Restore archived source files to original relative paths in a NEW directory."""
from pathlib import Path
import argparse,json,shutil,hashlib
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 package=Path(__file__).resolve().parents[1];dest=a.output.resolve()
 if dest.exists() and any(dest.iterdir()):raise RuntimeError('Choose a new empty destination; never overwrite working source')
 dest.mkdir(parents=True,exist_ok=True)
 data=json.loads((package/'archive/source_map.json').read_text(encoding='utf8'))
 for row in data['files']:
  src=(package/row['archived_path']).resolve();target=(dest/row['original_path']).resolve()
  if not src.is_relative_to(package) or not target.is_relative_to(dest):raise ValueError('Unsafe relative path')
  if hashlib.sha256(src.read_bytes()).hexdigest()!=row['archived_sha256']:raise ValueError('Archived source hash mismatch')
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
 print('Restored',len(data['files']),'source files to',dest)
if __name__=='__main__':main()

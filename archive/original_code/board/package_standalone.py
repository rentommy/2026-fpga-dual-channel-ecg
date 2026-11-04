from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parent
names=['run_scope_standalone.py','install_standalone.py','prepare_standalone.py']
manifest={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
archive=root/'ecg_standalone_20261104.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name in names:
        z.write(root/name,name)
    z.writestr('manifest.json',json.dumps(manifest,indent=2))
print(json.dumps(dict(path=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))

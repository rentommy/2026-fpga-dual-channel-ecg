"""Check assembled wheel against the SHA256 published by the official index."""
from pathlib import Path
import hashlib,html,json,re,urllib.request
ROOT=Path(__file__).resolve().parent
name='torch-2.7.1+cu128-cp312-cp312-win_amd64.whl'
with urllib.request.urlopen('https://download.pytorch.org/whl/cu128/torch/',timeout=60) as r:
    page=r.read().decode()
links=[html.unescape(u) for u in re.findall(r'href="([^"]+)"',page)]
match=next(u for u in links if urllib.parse.unquote(u.split('#')[0]).endswith(name))
expected=match.split('#sha256=')[1]
h=hashlib.sha256()
with (ROOT/'wheels'/name).open('rb') as f:
    for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
actual=h.hexdigest()
result={'official_link':match,'expected_sha256':expected,'actual_sha256':actual,'match':actual==expected}
(ROOT/'audit/cuda_wheel_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert actual==expected,result
print('Official SHA256 verified',actual)

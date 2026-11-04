"""Resumable range download of the official CUDA wheel, with strict byte ranges."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import urllib.request,time
URL='https://download-r2.pytorch.org/whl/cu128/torch-2.7.1%2Bcu128-cp312-cp312-win_amd64.whl'
SIZE=3273024349
DEST=Path(__file__).resolve().parent/'wheels'
CHUNK=8*1024*1024

def part(i):
    start=i*CHUNK;end=min(SIZE,start+CHUNK)-1;p=DEST/f'part_{i:03d}'
    if p.exists() and p.stat().st_size==end-start+1:return i
    for attempt in range(4):
        try:
            with p.open('wb') as f:
                for substart in range(start,end+1,1024*1024):
                    subend=min(end,substart+1024*1024-1)
                    request=urllib.request.Request(URL,headers={'Range':f'bytes={substart}-{subend}'})
                    with urllib.request.urlopen(request,timeout=30) as r:
                        expected=f'bytes {substart}-{subend}/{SIZE}'
                        if r.status!=206 or r.headers.get('Content-Range')!=expected:raise RuntimeError('Invalid byte range')
                        data=r.read()
                        if len(data)!=subend-substart+1:raise RuntimeError('Incomplete subrange')
                        f.write(data)
            if p.stat().st_size!=end-start+1:raise RuntimeError('Incomplete part')
            return i
        except Exception:
            if attempt==3:raise
            time.sleep(2)

if __name__=='__main__':
    DEST.mkdir(exist_ok=True);n=(SIZE+CHUNK-1)//CHUNK
    with ThreadPoolExecutor(max_workers=8) as pool:
        for k,f in enumerate(as_completed([pool.submit(part,i) for i in range(n)]),1):
            print('part',f.result(),'completed',k,'/',n,flush=True)
    wheel=DEST/'torch-2.7.1+cu128-cp312-cp312-win_amd64.whl'
    with wheel.open('wb') as f:
        for i in range(n):
            with (DEST/f'part_{i:03d}').open('rb') as src:
                while b:=src.read(8*1024*1024):f.write(b)
    print('assembled',wheel,flush=True)

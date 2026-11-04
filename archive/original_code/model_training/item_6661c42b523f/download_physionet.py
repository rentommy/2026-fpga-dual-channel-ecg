"""Download explicitly selected public WFDB data; never executes remote content."""
from pathlib import Path
import urllib.request,urllib.error,concurrent.futures,hashlib,json,time,re,argparse,datetime
ROOT=Path(__file__).resolve().parent
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def fetch(db,name):
    assert db in ('incartdb','svdb') and re.fullmatch(r'[A-Za-z0-9_.-]+',name)
    folder=ROOT/(db+'-1.0.0');folder.mkdir(exist_ok=True)
    target=folder/name
    canonical=f'https://physionet.org/files/{db}/1.0.0/{name}'
    url=f'https://physionet-open.s3.amazonaws.com/{db}/1.0.0/{name}'
    # Existing downloads are only reused with their own saved size/hash receipt.
    receipt=folder/(name+'.download.json')
    if target.exists() and receipt.exists():
        m=json.loads(receipt.read_text())
        if target.stat().st_size==m['bytes'] and digest(target)==m['sha256']:return m
    for attempt in range(4):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'ECG-research-download/1.0'})
            with urllib.request.urlopen(request,timeout=45) as response:
                expected=response.headers.get('Content-Length');part=folder/(name+'.part');h=hashlib.sha256();size=0
                with part.open('wb') as f:
                    while True:
                        chunk=response.read(64*1024)
                        if not chunk:break
                        f.write(chunk);h.update(chunk);size+=len(chunk)
                if expected and size!=int(expected):raise IOError('Incomplete HTTP body')
                if size==0:raise IOError('Empty file')
                part.replace(target)
                m={'url':url,'canonical_url':canonical,'file':name,'bytes':size,'sha256':h.hexdigest(),'http_content_length':expected,'downloaded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
                receipt.write_text(json.dumps(m,indent=2),encoding='utf-8');return m
        except Exception:
            if attempt==3:raise
            time.sleep(2*(attempt+1))
def main():
    p=argparse.ArgumentParser();p.add_argument('--metadata-only',action='store_true');args=p.parse_args()
    for db in ['svdb','incartdb']:
        receipts=[fetch(db,'RECORDS')];folder=ROOT/(db+'-1.0.0');records=(folder/'RECORDS').read_text().splitlines()
        assert all(re.fullmatch(r'[A-Za-z0-9]+',r) for r in records)
        extras=['ANNOTATORS']+(['record-descriptions.txt','files-patients-diagnoses.txt'] if db=='incartdb' else [])
        tasks=extras+[r+ext for r in records for ext in ['.hea','.atr']]
        if not args.metadata_only:tasks += [r+'.dat' for r in records]
        errors=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(fetch,db,name):name for name in tasks}
            for i,future in enumerate(concurrent.futures.as_completed(futures),1):
                name=futures[future]
                try:receipts.append(future.result())
                except Exception as e:errors.append({'file':name,'error':repr(e)});print('ERROR',db,name,repr(e),flush=True)
                if i%15==0 or i==len(tasks):print(db,i,'/',len(tasks),'files',round(sum(r['bytes'] for r in receipts)/1e6,1),'MB',flush=True)
        result={'database':db,'version':'1.0.0','official_page':f'https://physionet.org/content/{db}/1.0.0/','license':'Open Data Commons Attribution License v1.0; see official dataset page','records':records,'metadata_only':args.metadata_only,'files':receipts,'errors':errors,'completed':not errors}
        (folder/'download_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if errors:raise SystemExit(f'{db}: incomplete, rerun to retry missing files')
        print('COMPLETE',db,len(records),'records',flush=True)
if __name__=='__main__':main()

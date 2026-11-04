"""Download small source snapshots for inspection; never execute upstream code."""
from pathlib import Path
import urllib.request,json,hashlib,concurrent.futures
ROOT=Path(__file__).resolve().parent
REPOS=[('mondejar/ecg-classification','master'),
       ('MousaviSajad/ECG-Heartbeat-Classification-seq2seq-model','master'),
       ('andrelopes2001/patient-specific-ecg-classification','main'),
       ('mazder1/ECG','v1.0.1-5class'),
       ('nishujayaraj/ECG-Arrhythmia-Classification','main')]

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ECG-project-source-review','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=40) as r:
        data=r.read(16*1024*1024+1)
    if len(data)>16*1024*1024:raise ValueError('Source file too large')
    return data

def main():
    for repo,ref in REPOS:
        folder=ROOT/'sources'/repo.replace('/','__');folder.mkdir(parents=True,exist_ok=True)
        try:
            tree=json.loads(get(f'https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1'))
        except Exception as e:
            print('TREE_ERROR',repo,repr(e),flush=True);continue
        (folder/'tree.json').write_text(json.dumps(tree,indent=2),encoding='utf-8')
        paths=[x['path'] for x in tree['tree'] if x['type']=='blob']
        print(repo,'git_tree_sha',tree['sha'],'files',paths,flush=True)
        chosen=[]
        for entry in tree['tree']:
            name=entry['path'];lower=name.lower()
            if entry['type']!='blob' or entry.get('size',0)>15*1024*1024:continue
            relevant=lower.endswith(('.py','.m','.md','.txt','.yaml','.yml','.toml'))
            if repo.startswith('nishujayaraj/'):relevant=lower.endswith('.ipynb') and 'upgraded' in lower or lower=='readme.md'
            if not relevant or any(t in lower for t in ['third_party/','venv/','site-packages/','images/','figures/','mlruns/','logs/','results/','data/mitdb']):continue
            chosen.append(name)
        if len(chosen)>40:
            chosen=sorted(chosen,key=lambda p:(not any(k in p.lower() for k in ['readme','preprocess','split','loader','dataset','load_mit','feature','train_svm','seq_seq','model','personal','config','protocol']),len(p)))[:40]
        receipts=[];errors=[]
        def fetch(name):
            url=f"https://raw.githubusercontent.com/{repo}/{tree['sha']}/{urllib.parse.quote(name)}"
            data=get(url);p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            return {'file':name,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            tasks={pool.submit(fetch,p):p for p in chosen}
            for future in concurrent.futures.as_completed(tasks):
                try:receipts.append(future.result())
                except Exception as e:errors.append({'file':tasks[future],'error':repr(e)})
        (folder/'provenance.json').write_text(json.dumps({'repo':repo,'ref':ref,'git_tree_sha':tree['sha'],'files':receipts,'errors':errors},indent=2),encoding='utf-8')
        print('SAVED',repo,len(receipts),'errors',errors,flush=True)
    print('SOURCE_REVIEW_DOWNLOAD_COMPLETE',flush=True)

if __name__=='__main__':main()

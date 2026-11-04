"""Exploratory annotation-subtype and time-position strata; never select hyperparameters."""
import argparse,csv,json
from pathlib import Path
from pipeline import ROOT,table

def main(folder):
    with open(folder/'val_predictions.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    a=[r for r in rows if r['label']=='A'];strata=[]
    def add(name,rs):
        n=len(rs);hit=sum(r['prediction']=='A' for r in rs)
        strata.append({'stratum':name,'windows':n,'detected':hit,'recall':hit/n if n else None,
          'records':len({r['group'] for r in rs})})
    for db in sorted({r['database'] for r in a}):add(db,[r for r in a if r['database']==db])
    for r in a:r['raw_counts']=json.loads(r['annotation_counts'])
    add('native_A_without_S',[r for r in a if r['raw_counts'].get('A',0)>0 and not r['raw_counts'].get('S',0)])
    add('mapped_S_without_A',[r for r in a if r['raw_counts'].get('S',0)>0 and not r['raw_counts'].get('A',0)])
    add('mixed_A_S',[r for r in a if r['raw_counts'].get('S',0)>0 and r['raw_counts'].get('A',0)>0])
    for start in (0,2,4,6,8):
        add(f'single_A_position_{start}_{start+2}s',[r for r in a if int(r['a_count'])==1 and start<=float(r['a_first_sec'])<start+2])
    table(folder/'A_exploratory_strata.csv',strata)
    print(json.dumps(strata,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args();main(ROOT/args.folder)

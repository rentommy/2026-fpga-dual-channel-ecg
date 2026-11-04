from pathlib import Path
import json,collections
import wfdb

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
ORIGINAL=PROJECT.parent/'项目复现/ECG_ren'
SAMPLES=PROJECT.parent/'样本'
SOURCES=[('mit',ORIGINAL/'mit-bih-arrhythmia-database-1.0.0','MLII'),
 ('edb',ORIGINAL/'european-st-t-database-1.0.0','MLIII'),
 ('stdb',ORIGINAL/'mit-bih-st-change-database-1.0.0','ECG'),
 ('sddb',ORIGINAL/'sudden-cardiac-death-holter-database-1.0.0','ECG'),
 ('incart',SAMPLES/'incartdb-1.0.0','II'),('svdb',SAMPLES/'svdb-1.0.0','ECG1')]

def main():
    rows=[];summaries={}
    for db,folder,preferred in SOURCES:
        counts=collections.Counter();coverage=collections.defaultdict(list);missing=[]
        for rec in (folder/'RECORDS').read_text().splitlines():
            h=wfdb.rdheader(str(folder/rec));annfile=folder/(rec+'.atr')
            if not annfile.exists():missing.append(rec);continue
            a=wfdb.rdann(str(folder/rec),'atr');c=collections.Counter(a.symbol);counts.update(c)
            for k in c:coverage[k].append(rec)
            lead=preferred if preferred in h.sig_name else h.sig_name[0]
            rows.append({'db':db,'record':rec,'folder':str(folder),'lead':lead,'preferred_lead_available':preferred in h.sig_name,
                         'fs':h.fs,'samples':h.sig_len,'labels':dict(c),'comments':h.comments})
        summaries[db]={'records_with_atr':sum(r['db']==db for r in rows),'records_missing_atr':missing,
                       'counts':dict(counts),'records_per_label':{k:len(v) for k,v in coverage.items()},
                       'label_records':dict(coverage)}
    (ROOT/'inventory.json').write_text(json.dumps({'summary':summaries,'records':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    for db,s in summaries.items():print(db,s['records_with_atr'],'missing',s['records_missing_atr'],'counts',s['counts'],flush=True)

if __name__=='__main__':main()

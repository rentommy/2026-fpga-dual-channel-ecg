"""Standard-library-only inventory; no edits to source files."""
from pathlib import Path
from collections import Counter
import csv, hashlib, json

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'项目复现'/'ECG_ren'

def digest(f):
    h=hashlib.sha256()
    with f.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def labels(f):
    with f.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.reader(stream);next(reader)
        return [r[0] for r in reader]

def main():
    out=ROOT/'audit';out.mkdir(exist_ok=True)
    inventory=[]
    for f in sorted((SOURCE/'Data').rglob('*.csv')):
        row={'path':str(f.relative_to(SOURCE)),'bytes':f.stat().st_size,'sha256':digest(f)}
        if 'symbols' in f.name or 'Y_' in f.name:
            ys=labels(f);row.update(rows=len(ys),labels=dict(Counter(ys)))
        inventory.append(row)
    diffs=[]
    for a,b in [('0MLIIIsymbols_data.csv','csv/30Y_eu_MLIII.csv'),('3ECGsymbols_data.csv','csv/3ECGsymbols_data.csv')]:
        x=labels(SOURCE/'Data'/a);y=labels(SOURCE/'Data'/b)
        diffs.append({'current':a,'alternative':b,'current_rows':len(x),'alternative_rows':len(y),
          'different_rows':sum(i!=j for i,j in zip(x,y)),
          'transitions':dict(Counter(f'{j} -> {i}' for i,j in zip(x,y) if i!=j)),
          'warning':'rowwise comparison does not establish identical signal alignment'})
    data={'files':inventory,'label_differences':diffs}
    (out/'legacy_inventory.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(diffs,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

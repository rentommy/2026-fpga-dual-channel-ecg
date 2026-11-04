"""Quantify artifact contamination of the frozen benchmark timing stream."""
from pathlib import Path
import collections, csv, json
import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
SOURCE = PROJECT.parent / '项目复现/ECG_ren/mit-bih-arrhythmia-database-1.0.0'
EVENTS = set('NLRaVFJASEj/QBenfr') | {'|'}
rows = list(csv.DictReader((PROJECT / 'benchmark_03/data/beats.csv').open(encoding='utf-8-sig')))
per_record = collections.defaultdict(list)
for row in rows:
    if row['symbol'] != '|':
        per_record[row['record']].append(row)
counts = collections.Counter()
affected = collections.Counter()
examples = []
for record, beats in per_record.items():
    ann = wfdb.rdann(str(SOURCE / record), 'atr')
    keep = np.array([s in EVENTS for s in ann.symbol])
    points = ann.sample[keep]
    symbols = np.array(ann.symbol)[keep]
    index = {int(p): i for i,p in enumerate(points)}
    for beat in beats:
        j = index[int(beat['sample'])]
        counts[beat['symbol']] += 1
        # Directly affected pre/post intervals and midpoint bounds, not all trailing-RR features.
        if symbols[j-1] == '|' or symbols[j+1] == '|':
            affected[beat['symbol']] += 1
            if len(examples) < 12:
                examples.append({'record': record, 'sample': int(points[j]), 'label': beat['symbol'],
                                 'previous_symbol': symbols[j-1], 'next_symbol': symbols[j+1]})
result = {'finding': 'Non-beat artifact | participates in the frozen RR and midpoint stream',
          'physiological_targets': sum(counts.values()), 'directly_affected': sum(affected.values()),
          'directly_affected_per_label': dict(affected), 'total_per_label': dict(counts),
          'examples': examples,
          'scope': 'Direct pre/post RR and midpoint effects only; trailing median effects not counted. No model rerun; causal accuracy impact unknown.'}
(ROOT / 'existing_rr_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))

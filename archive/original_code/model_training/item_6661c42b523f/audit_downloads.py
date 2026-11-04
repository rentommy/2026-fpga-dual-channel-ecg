"""Audit downloaded WFDB records without changing labels or waveforms."""
from pathlib import Path
import json, hashlib, collections, re, csv
import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parent

def audit(db):
    folder = ROOT / (db + '-1.0.0')
    manifest = json.loads((folder / 'download_manifest.json').read_text(encoding='utf-8'))
    assert manifest['completed'] and not manifest['metadata_only']
    errors = []
    for item in manifest['files']:
        p = folder / item['file']
        if p.stat().st_size != item['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
            errors.append('Receipt mismatch: ' + p.name)
    patients = {}
    if db == 'incartdb':
        current = None
        for line in (folder / 'files-patients-diagnoses.txt').read_text().splitlines():
            if re.fullmatch(r'patient\s+\d+', line.strip()):
                current = line.strip().replace(' ', '_')
            elif re.fullmatch(r'I\d+(?:\s+I\d+)*', line.strip()):
                for record in line.split():
                    assert record not in patients and current is not None
                    patients[record] = current
        assert set(patients) == set(manifest['records'])
    counts = collections.Counter()
    in_bounds_counts = collections.Counter()
    excluded_annotations = []
    groups = collections.defaultdict(set)
    records_by_label = collections.defaultdict(set)
    rows = []
    for name in manifest['records']:
        record = wfdb.rdrecord(str(folder / name), physical=False)
        ann = wfdb.rdann(str(folder / name), 'atr')
        count = collections.Counter(ann.symbol)
        counts.update(count)
        group = patients.get(name, 'record_' + name)
        for label in count:
            groups[label].add(group)
            records_by_label[label].add(name)
        checksum = np.sum(record.d_signal, axis=0, dtype=np.int64) % 65536
        expected = np.asarray(record.checksum, dtype=np.int64) % 65536
        ok = bool(np.array_equal(checksum, expected))
        valid = (ann.sample >= 0) & (ann.sample < record.sig_len)
        bounds = bool(np.all(valid))
        in_bounds_counts.update(s for s, v in zip(ann.symbol, valid) if v)
        for i in np.flatnonzero(~valid):
            excluded_annotations.append({'record': name, 'annotation_index': int(i),
                                         'sample': int(ann.sample[i]), 'symbol': ann.symbol[i],
                                         'signal_length': record.sig_len, 'reason': 'outside signal bounds; exclude from extraction'})
        shape = record.d_signal.shape == (record.sig_len, record.n_sig)
        if not (ok and shape):
            errors.append({'record': name, 'checksum': ok, 'annotation_bounds': bounds, 'shape': shape})
        rows.append({'record': name, 'group': group, 'fs': record.fs, 'samples': record.sig_len,
                     'leads': '|'.join(record.sig_name), 'checksum_ok': ok, 'annotation_bounds_ok': bounds,
                     'labels': json.dumps(dict(count), ensure_ascii=False)})
    result = {'database': db, 'records': len(rows), 'groups': len({r['group'] for r in rows}),
              'group_identity': 'official patient IDs' if patients else 'record proxy; unique patient identity unconfirmed',
              'bytes': sum(f['bytes'] for f in manifest['files']), 'annotation_counts': dict(sorted(counts.items())),
              'in_bounds_annotation_counts': dict(sorted(in_bounds_counts.items())),
              'excluded_annotations': excluded_annotations, 'all_annotations_in_bounds': not excluded_annotations,
              'groups_per_label': {k: len(v) for k,v in sorted(groups.items())},
              'records_per_label': {k: len(v) for k,v in sorted(records_by_label.items())},
              'errors': errors, 'passed': not errors,
              'pass_scope': 'download receipts, signal decoding/checksums/shape; annotation exclusions must be applied before training',
              'checks': ['local SHA256 receipts (not publisher hashes)', 'WFDB digital checksums on every lead',
                         'annotation bounds', 'signal shape', 'patient mapping coverage for INCART']}
    (folder / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (folder / 'record_inventory.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result

if __name__ == '__main__':
    results = [audit(db) for db in ['svdb', 'incartdb']]
    (ROOT / 'data_audit.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if not all(r['passed'] for r in results):
        raise SystemExit('Audit failed; inspect errors before use.')

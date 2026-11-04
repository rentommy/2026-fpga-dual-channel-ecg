import json,collections
from pipeline import ROOT,DATA,CLASSES,SOURCES,save

m=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'));summary={}
lines=['# 六库实际数据覆盖','','所有数字为当前滤波、边界检查及标签筛选后的数据。记录数与患者数不能混用。','','| 库 | 划分 | 记录数 | 分组数 | A | F | L | N | R | S | V | 伪迹 |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for db,_,_ in SOURCES:
    summary[db]={}
    for split in ['train','val','test']:
        rows=[r for r in m['records'] if r['db']==db and r['split']==split]
        if not rows:continue
        counts=collections.Counter()
        for r in rows:counts.update(r['counts'])
        group_counts={c:len({r['group'] for r in rows if r['counts'].get(c,0)}) for c in CLASSES}
        summary[db][split]={'records':len(rows),'groups':len({r['group'] for r in rows}),'counts':dict(counts),'groups_per_class':group_counts}
        lines.append('| '+db+' | '+split+' | '+str(len(rows))+' | '+str(len({r['group'] for r in rows}))+' | '+' | '.join(str(counts[c]) for c in CLASSES)+' |')
lines+=['','STDB和SVDB的分组数只表示记录代理，唯一患者身份未确认，因此两库整体仅用于训练。EDB采用官方79位患者关系，INCART采用官方32位患者映射，MIT201/202同组。',
        'SDDB仅接入12条带人工审核atr记录，11条缺少人工参考标注的记录保留原样但不作监督训练。B仍排除，原始B没有改成L/R。',
        '“完整接入”不意味着把测试患者也用于训练；每个可监督记录均归入训练、验证或测试之一。所有训练目标都会在候选权重保存前遍历至少一次。']
save(ROOT/'coverage.json',summary)
(ROOT/'数据覆盖.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Coverage saved')

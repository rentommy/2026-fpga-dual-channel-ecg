"""Inventory existing raw-label record coverage; does not pool datasets or fit."""
import json
from collections import defaultdict
from benchmark import ROOT, CLASSES, table

manifest=json.loads((ROOT.parent/'data/manifest.json').read_text(encoding='utf-8'))
groups=defaultdict(list)
details=[]
for r in manifest['records']:
    for cls in CLASSES:
        n=int(r['counts'].get(cls,0))
        if not n:continue
        key=(r['database'],r['lead'],cls)
        groups[key].append((r['record'],n))
        details.append({'database':r['database'],'lead':r['lead'],'class':cls,'record':r['record'],'count':n})
table(ROOT/'existing_source_coverage.csv',details)
lines=['# 现有资料的原始标签来源覆盖','','依据第二轮保存的原始逐拍清单统计；未重新混合训练。这里的来源数是记录数，跨记录受试者身份仍需核实。导联名称相同也不保证采集条件相同。','',
       '| 数据库 | 导联 | 原始标签 | 拍数 | 有该标签的记录数 |','|---|---|---|---:|---:|']
for (db,lead,cls),items in sorted(groups.items()):
    label=cls.replace('|','\\|')
    lines.append(f'| {db} | {lead} | {label} | {sum(n for _,n in items)} | {len(items)} |')
lines+=['','B 来源明细：']
for r in details:
    if r['class']=='B':lines.append(f'- {r["database"]} / {r["record"]} / {r["lead"]}：{r["count"]} 拍。')
lines+=['','补数时应先核实标签定义与受试者身份，再按导联和数据库建立独立评估；不应把其他原始符号改名为 B/S 来补齐。',
    '详细记录列表保存于 existing_source_coverage.csv，可直接用于选择后续数据审核对象。']
(ROOT/'现有资料标签覆盖.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Existing source inventory complete.')

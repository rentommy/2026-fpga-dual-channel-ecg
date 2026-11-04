# 现有资料的原始标签来源覆盖

依据第二轮保存的原始逐拍清单统计；未重新混合训练。这里的来源数是记录数，跨记录受试者身份仍需核实。导联名称相同也不保证采集条件相同。

| 数据库 | 导联 | 原始标签 | 拍数 | 有该标签的记录数 |
|---|---|---|---:|---:|
| european-st-t-database-1.0.0 | MLIII | F | 246 | 6 |
| european-st-t-database-1.0.0 | MLIII | N | 375506 | 47 |
| european-st-t-database-1.0.0 | MLIII | S | 767 | 35 |
| european-st-t-database-1.0.0 | MLIII | V | 1455 | 24 |
| european-st-t-database-1.0.0 | MLIII | \| | 64 | 8 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | A | 2544 | 27 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | F | 802 | 17 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | L | 8063 | 4 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | N | 74722 | 38 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | R | 7246 | 6 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | S | 2 | 1 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | V | 7116 | 35 |
| mit-bih-arrhythmia-database-1.0.0 | MLII | \| | 132 | 19 |
| mit-bih-st-change-database-1.0.0 | ECG | N | 74978 | 28 |
| mit-bih-st-change-database-1.0.0 | ECG | S | 815 | 13 |
| mit-bih-st-change-database-1.0.0 | ECG | V | 322 | 13 |
| sudden-cardiac-death-holter-database-1.0.0 | ECG | B | 54723 | 1 |
| sudden-cardiac-death-holter-database-1.0.0 | ECG | F | 309 | 11 |
| sudden-cardiac-death-holter-database-1.0.0 | ECG | N | 745441 | 12 |
| sudden-cardiac-death-holter-database-1.0.0 | ECG | S | 382 | 7 |
| sudden-cardiac-death-holter-database-1.0.0 | ECG | V | 23584 | 12 |
| sudden-cardiac-death-holter-database-1.0.0 | ECG | \| | 16026 | 12 |

B 来源明细：
- sudden-cardiac-death-holter-database-1.0.0 / 36 / ECG：54723 拍。

补数时应先核实标签定义与受试者身份，再按导联和数据库建立独立评估；不应把其他原始符号改名为 B/S 来补齐。
详细记录列表保存于 existing_source_coverage.csv，可直接用于选择后续数据审核对象。

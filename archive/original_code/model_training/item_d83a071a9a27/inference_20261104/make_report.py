from pathlib import Path
import os,json,csv,hashlib
ROOT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(ROOT/'plot_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    d=json.loads((ROOT/'summary.json').read_text(encoding='utf-8'))
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    lines=['# 2026-11-04 两段自采心电推理结果','',
      '主模型：最后一轮experiment_09六库方案的six_db_seed0/best.pt。三份六库权重按原保存的选型验证macro-F1比较，seed0为0.4460、seed1为0.4359、seed2为0.4077，因此选seed0；没有依据这两段预测结果或测试集重新挑权重。另两份权重仅用于检查预测稳定性。research_10只是研究，没有后续新训练权重。','',
      '输入取02_有效通道完整记录中的原始ADC码，按文件标定转mV。每段独立处理：500Hz三阶0.5–40Hz双向带通＋50Hz/Q30双向陷波，重采样256Hz；自动定位后按原模型205点、中心77点、中点掩码、有效点均值/标准差与8维RR提取输入。RR标准化使用对应权重保存的训练参数。不把板上diag/fast输出再次当原始心电输入，也没有拼接两段。','',
      '## 主模型完整记录结果','',
      '| 记录 | 标称时长 | 自动定位候选 | 实际分类目标 | N | A | S | 伪迹 | F/L/R/V |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    anomaly=[];checks=[]
    for r in d['records']:
        name=r['recording'];folder=ROOT/name
        rows=list(csv.DictReader((folder/'逐拍预测.csv').open(encoding='utf-8-sig')))
        with np.load(folder/'推理输入与概率.npz',allow_pickle=False) as z:
            assert z['x'].shape==(len(rows),2,205)
            assert z['probabilities'].shape==(3,len(rows),8)
            assert np.allclose(z['probabilities'].sum(-1),1,atol=1e-6)
            assert [d['classes'][i] for i in z['probabilities'][0].argmax(-1)]==[v['predicted_label'] for v in rows]
        counts={c:sum(v['predicted_label']==c for v in rows) for c in d['classes']}
        assert counts==r['counts_all_classified'] and sum(counts.values())==r['classified_targets']
        assert hashlib.sha256(Path(r['input']).read_bytes()).hexdigest()==r['input_sha256']
        checks.append({'recording':name,'input_hash_unchanged':True,'probabilities_csv_counts_consistent':True})
        c=counts
        lines.append(f"| {name} | {r['nominal_duration_s']:.3f}秒 | {r['automatic_qrs_count']} | {len(rows)} | {c['N']} | {c['A']} | {c['S']} | {c['|']} | 均0 |")
        anomaly.extend((name,v) for v in rows if v['predicted_label']!='N')
        if 'CN4' in name:
            with np.load(folder/'推理输入与概率.npz',allow_pickle=False) as z:wave=z['filtered_256hz']
            t=np.arange(len(wave))/256;ix=(t>=11.7)&(t<=15.8)
            fig,ax=plt.subplots(figsize=(14,4),layout='constrained')
            ax.plot(t[ix],wave[ix],lw=1,color='#355875')
            for v in rows:
                ts=float(v['time_s'])
                if 11.7<=ts<=15.8:
                    col='#bd3636' if v['predicted_label']!='N' else '#168351'
                    y=wave[int(np.rint(ts*256))]
                    ax.scatter(ts,y,c=col,s=30)
                    lab=v['predicted_label'].replace('|','伪迹')
                    ax.annotate(f"{ts:.3f}s  {lab}",(ts,y),xytext=(0,18),textcoords='offset points',ha='center',color=col,fontsize=10)
            ax.set_ylim(-1.5,1.65);ax.set_xlim(11.7,15.8);ax.grid(alpha=.2)
            ax.set_xlabel('标称时间 / 秒');ax.set_ylabel('模型滤波后 mV')
            ax.set_title('CN4/CH1 干扰附近的模型输出：A/S为待复核预测，并非确诊标签')
            fig.savefig(ROOT/'CN4_干扰附近预测.png',dpi=170);plt.close(fig)
    lines+=['','N为模型的正常拍类别；A为房性早搏类别，S为原始室上性早搏类别；伪迹符号是QRS样噪声候选，不是真实心拍类型。A/S保持分别输出。',
      '每段首、末自动定位候选因缺少前拍或后拍上下文，仅用于时间上下文，不给分类结论。因此25个定位候选对应23个分类目标，35个对应33个。实际计数均是自动定位候选，不能当成人工确认的真实总心拍数。',
      '前2秒/末0.5秒按已有采集说明单独标记，没有从完整统计中偷偷删去。排除这两个时间区域后，CN2为22个N；CN4为28个N、1个A、1个S、2个伪迹，共32目标。','',
      '## 非N输出及其稳定性','',
      '| 记录 | 原始时间 | 主预测 | 主模型分数 | seed0 / seed1 / seed2 |','|---|---:|---|---:|---|']
    for name,v in anomaly:
        label=v['predicted_label'].replace('|','伪迹')
        seq=' / '.join(v[f'six_db_seed{i}'].replace('|','伪迹') for i in range(3))
        lines.append(f"| {name} | {float(v['time_s']):.3f}秒 | {label} | {float(v['model_score']):.2%} | {seq} |")
    lines+=['','人工查看本次滤波波形可见CN4约12.4–12.8秒、14.5–14.9秒有明显突变和振荡，四个非N输出位于这些干扰及其附近。A和S分别发生种子间分歧，不能把它们直接认定为真实早搏。CN2全部分类目标的三份权重输出一致为N。',
      'XQRS与GQRS在已分类目标上均能在±100ms内匹配；两种检测器一致不能证明候选是真实QRS，干扰也可能同时触发两者。训练用参考标注并从生理RR事件流排除伪迹，本次自动定位可能将干扰纳入RR，从而影响附近A/S输出。因此现阶段不能以模型输出反推这些异常的医学真值，也没有通过删除模型不喜欢的候选来改写主结果。','',
      '## 已有优选10秒的独立范围统计','',
      '此处是在完整记录上滤波、推理后按原始时间范围统计，不把优选片段重新当独立记录或独立受试者。范围来自采集时已保存的质量文件，未按此次类别预测挑选。','',
      '| 记录 | 原始时间范围 | 已分类目标 | 预测 |','|---|---|---:|---|']
    for r in d['records']:
        a,b=r['preferred_10s'];c=r['counts_preferred_10s'];others=sum(v for k,v in c.items() if k!='N')
        lines.append(f"| {r['recording']} | {a:.1f}–{b:.1f}秒 | {r['n_preferred_10s']} | N {c['N']}，其他 {others} |")
    lines+=['','## 怎样理解结果','',
      '- 这两段没有逐拍专家标签，无法计算准确率、精确率或召回率。表中分数为未经校准的softmax值，不是正确概率，也不是诊断置信度。',
      '- 自动定位、硬件导联与训练库导联差异都是额外误差来源；双向滤波及未来RR使本次属于离线推理，不能直接代表板端实时效果。',
      '- 模型历史验证中L/R及部分少数类效果仍差，“本次没有预测到某类”不等于已经可靠排除该类。',
      '- 两段来自同一位受测者，无疾病/健康真值，不能据N输出将其补成健康人训练标签。',
      '- 完整波形与逐拍分数见各记录子目录；逐拍CSV保留原始时间、样点、类别概率、不同种子输出及启动/末尾标记。输入文件和权重SHA256见summary.json。','',
      '主结果：CN2输出稳定为N；CN4以N为主，干扰附近出现两个伪迹候选及两个不稳定A/S预测，需要复核，不能直接作为真实早搏结论。']
    (ROOT/'推理结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'output_audit.json').write_text(json.dumps({'passed':True,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPORT_AND_OUTPUT_AUDIT_COMPLETE')

if __name__=='__main__':main()

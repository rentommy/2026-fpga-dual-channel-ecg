"""Verify downloaded board recordings and export reproducible training candidates."""
from pathlib import Path
import argparse, base64, hashlib, json, shutil, subprocess, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT=next(p for p in Path(__file__).resolve().parents if (p/'src/hls/ecg_filter.cpp').is_file())
ROOT=PROJECT/'模型训练/采集/2026-11-04_真实心电_已保存记录'
TRANSPORT=Path(r'C:\Users\rentommy\AppData\Local\Packages\sandbox.{ea71cb85-9409-4bc4-82eb-56899d619f96}\AC\Temp/browser-use/assets/97c9bf95-49e3-49e1-a4b3-57d276b1b52c/629b64a8dfc7be76.png')
EXPECTED='5c85a0e97a33fb0b33227516d540dfa85debad549641a34d068fef696f8a1099'
FS=500
MV=2.42/6/(2**23-1)*1000

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def quality(x,diag):
    a=x.astype(float); a-=a.mean()
    freq=np.fft.rfftfreq(len(a),1/FS)
    power=np.abs(np.fft.rfft(a*np.hanning(len(a))))**2
    total=max(power[(freq>=.5)&(freq<=150)].sum(),1e-20)
    def band(lo,hi): return float(power[(freq>=lo)&(freq<=hi)].sum()/total)
    d=diag.astype(float)*MV
    # Engineering screening only: baseline stability, raw mains and high-frequency energy.
    smooth=np.convolve(d,np.ones(250)/250,mode='same')[250:-250]
    span=float(np.percentile(d,99)-np.percentile(d,1))
    drift=float(np.std(smooth))/max(span,1e-9)
    clipping=float(np.mean(np.abs(x.astype(np.int64))>=8380000))
    centered=d-np.median(d)
    lo,hi=np.percentile(centered,[.5,99.5])
    oriented=centered if abs(hi)>=abs(lo) else -centered
    opposite_ratio=float(max(0,-oriented.min())/max(float(np.percentile(oriented,99.5)),1e-9))
    transient_penalty=max(0,opposite_ratio-.5)
    return dict(raw_mains_fraction=band(49,51),raw_high_frequency_fraction=band(45,150),
                diag_p1_p99_mV=span,diag_baseline_ratio=drift,diag_opposite_excursion_ratio=opposite_ratio,
                clipped_fraction=clipping,
                screening_score=band(49,51)+band(45,150)+2*drift+2*transient_penalty+100*clipping)

def plot(path,rows,title):
    im=Image.new('RGB',(1500,160+240*len(rows)),'white'); draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    draw.text((45,20),title,font=font,fill='#152a3b')
    for j,(label,y) in enumerate(rows):
        y=np.asarray(y,dtype=float); top=90+j*240; center=float(np.median(y))
        span=max(float(np.max(np.abs(y-center)))*1.05,.001)
        draw.text((45,top-35),f'{label}   中位值 {center:.4f} mV；纵轴 ±{span:.4f} mV',font=small,fill='black')
        for t in range(int((len(y)-1)/FS)+1):
            px=90+t*1350/max((len(y)-1)/FS,.001)
            draw.line((px,top,px,top+155),fill='#d4dfe6')
            draw.text((px,top+160),f'{t}s',font=small,fill='#526674')
        draw.line((90,top+78,1440,top+78),fill='#aabac6')
        points=[(90+i*1350/(len(y)-1),top+78-(v-center)*72/span) for i,v in enumerate(y)]
        draw.line(points,fill='#007b91',width=2)
    im.save(path)

def main():
    import zipfile
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,help='Use an existing board export ZIP instead of the browser transport')
    parser.add_argument('--refresh-derived',action='store_true',help='Regenerate only this verified export in its existing directory')
    args=parser.parse_args()
    if ROOT.exists() and not args.refresh_derived: raise FileExistsError('Refusing to overwrite existing export: '+str(ROOT))
    ROOT.mkdir(parents=True,exist_ok=args.refresh_derived)
    original=ROOT/'01_板端原始文件'; original.mkdir(exist_ok=True)
    data=args.archive.read_bytes() if args.archive else base64.b64decode(Image.open(TRANSPORT).info['ecg_export_zip_base64'])
    assert hashlib.sha256(data).hexdigest()==EXPECTED
    archive=original/'板端完整导出包.zip'; archive.write_bytes(data)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
        z.extractall(original)
    metadata=json.loads((original/'metadata.json').read_text())
    for name,item in metadata['files'].items():
        assert digest(original/name)==item['sha256'],name
    scripts=ROOT/'05_复现与说明'; scripts.mkdir(exist_ok=True)
    for name in ['ecg_filter.cpp','ecg_filter.h','ecg_filter_coef.h']:
        shutil.copy2(PROJECT/'src/hls'/name,scripts/name)
    oracle=(PROJECT/'sim/channel_oracle.cpp').read_text(encoding='utf-8').replace('../src/hls/ecg_filter.h','ecg_filter.h')
    (scripts/'channel_oracle.cpp').write_text(oracle,encoding='utf-8')
    # Build the current project oracle rather than trusting a stale executable.
    executable=scripts/'channel_oracle.exe'
    subprocess.run(['D:/msys64/ucrt64/bin/g++.exe','-std=c++17','-O2',
                    str(scripts/'channel_oracle.cpp'),str(scripts/'ecg_filter.cpp'),
                    '-o',str(executable)],check=True,capture_output=True,text=True)
    full=ROOT/'02_有效通道完整记录'; full.mkdir(exist_ok=True)
    selected=ROOT/'03_优选连续片段'; selected.mkdir(exist_ok=True)
    pictures=ROOT/'04_波形与质量'; pictures.mkdir(exist_ok=True)
    sessions=[]; windows=[]
    for folder,ch in metadata['selected_channels'].items():
        source=original/folder
        raw=np.load(source/'raw.npy',allow_pickle=False)
        assert raw.dtype==np.int32 and raw.ndim==2 and raw.shape[1]==2
        summary=json.loads((source/'run_summary.json').read_text())
        assert summary['source']=='adc' and summary['overruns']==0 and summary['bad_frames']==0 and summary['error'] is None
        assert summary['samples_per_channel']==len(raw)
        tag='CN2_CH2_最新记录' if ch==2 else 'CN4_CH1_RLD修正记录'
        packed=np.zeros((len(raw),8),dtype=np.int32); packed[:,:2]=raw
        infile=scripts/(tag+'_oracle_input.bin'); outfile=scripts/(tag+'_oracle_output.bin')
        packed.tofile(infile)
        result=subprocess.run([str(executable),str(infile),str(outfile)],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        out=np.fromfile(outfile,dtype=np.int32).reshape(-1,8,2)[:,:2,:]
        actual=np.load(source/'filtered_last4s.npy',allow_pickle=False)
        matches=[]
        for lag in range(65):
            end=len(out)-lag
            if end>=len(actual):
                error=int(np.max(np.abs(out[end-len(actual):end].astype(np.int64)-actual)))
                matches.append((error,lag))
        error,lag=min(matches)
        assert error==0,(tag,error,lag)
        channel_raw=raw[:,ch-1]; paths=out[:,ch-1,:]
        np.savez_compressed(full/(tag+'.npz'),raw_codes=channel_raw,diag_codes=paths[:,0],fast_codes=paths[:,1],
                            sample_index=np.arange(len(raw)),fs_hz=FS,mV_per_code=MV,channel=ch,
                            subject_group='single_reported_subject_20261104')
        np.savetxt(full/(tag+'.csv'),np.column_stack((np.arange(len(raw)),np.arange(len(raw))/FS,channel_raw,
                     channel_raw*MV,paths[:,0]*MV,paths[:,1]*MV)),delimiter=',',
                     header='source_sample_index,time_nominal_s,raw_adc_code,raw_mV,diag_reference_mV,fast_reference_mV',
                     fmt=['%d','%.6f','%d','%.9f','%.9f','%.9f'],comments='')
        candidates=[]
        for start in range(1000,len(raw)-5000-250+1,250):
            stop=start+5000
            q=quality(channel_raw[start:stop],paths[start:stop,0])
            row=dict(recording=tag,start_sample=start,stop_sample_exclusive=stop,start_nominal_s=start/FS,
                     duration_nominal_s=10,**q)
            windows.append(row); candidates.append(row)
        best=min(candidates,key=lambda v:v['screening_score'])
        start=best['start_sample']; stop=best['stop_sample_exclusive']
        np.savez_compressed(selected/(tag+'_优选10秒.npz'),raw_codes=channel_raw[start:stop],
                    diag_codes=paths[start:stop,0],fast_codes=paths[start:stop,1],
                    source_sample_index=np.arange(start,stop),fs_hz=FS,mV_per_code=MV,channel=ch,
                    subject_group='single_reported_subject_20261104')
        np.savetxt(selected/(tag+'_优选10秒.csv'),np.column_stack((np.arange(start,stop),np.arange(5000)/FS,
                    channel_raw[start:stop],channel_raw[start:stop]*MV,paths[start:stop,0]*MV,paths[start:stop,1]*MV)),
                    delimiter=',',header='source_sample_index,time_from_segment_start_s,raw_adc_code,raw_mV,diag_reference_mV,fast_reference_mV',
                    fmt=['%d','%.6f','%d','%.9f','%.9f','%.9f'],comments='')
        plot(pictures/(tag+'_优选10秒.png'),[('原始采样（含电极直流偏置）',channel_raw[start:stop]*MV),
             ('保真路径：项目定点参考重放',paths[start:stop,0]*MV),
             ('快速路径：项目定点参考重放',paths[start:stop,1]*MV)],tag+'：独立连续片段，未拼接心拍')
        plot(pictures/(tag+'_完整保真波形.png'),[('保真路径（完整，含启动瞬态）',paths[:,0]*MV)],tag)
        sessions.append(dict(recording=tag,selected_channel=ch,source_folder=folder,raw_samples=len(raw),
              recorded_nominal_seconds=len(raw)/FS,source='human_electrode_adc',rld_sens='0x2C' if ch==2 else '0x23',
              board_output_verification=dict(max_abs_error_codes=error,last_draw_lag_samples=lag,comparison_samples=2000),
              preferred_segment=best,whole_quality_after_2s=quality(channel_raw[1000:],paths[1000:,0]),
              nominal_path_delay_samples=dict(diag=174,fast=15)))
    (pictures/'质量与溯源.json').write_text(json.dumps(dict(fs_nominal_hz=FS,mV_per_code=MV,sessions=sessions),ensure_ascii=False,indent=2),encoding='utf-8')
    with (pictures/'候选窗口质量.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(windows[0])); w.writeheader();w.writerows(windows)
    shutil.copy2(__file__,scripts/Path(__file__).name)
    (ROOT/'README_请先阅读.md').write_text('''# 2026-11-04 实际电极心电数据

这是本次调试中已保存的两段连续人体电极记录，不是芯片内部测试信号，也不是重启后的全部实时数据。标称采样率500 Hz，ADS1292、24位、增益6、参考电压2.42 V。板卡时钟错误，不采用其文件时间作为采集日期；具体时刻未知。

## 从哪里开始

- `03_优选连续片段`：每段原始记录选一个10秒连续窗口，CSV可直接读，NPZ保留整数ADC码。
- `02_有效通道完整记录`：两段各约23.78秒的完整有效通道数据，保留启动瞬态，以便自行筛选。
- `01_板端原始文件`：完整导出包及未经修改的原始双通道数组、板上最后4秒滤波输出、日志和质量记录。只有所标注通道接着电极，另一路悬空不应作为心电样本。
- `04_波形与质量`：完整/优选片段图、逐窗口质量指标和源文件索引。
- `05_复现与说明`：本次导出脚本、当前项目定点滤波实现与重放程序。

最新记录是CN2/CH2；CN4/CH1是之前修正RLD后的记录。两段来自同一位受测者的连续调试，不是同步双导联，不是两个独立受试者，不能拼接成连续记录。

## 数值与滤波

电压换算：ADC码×(2.42/6/(2^23−1))×1000，单位mV；这是名义标定，不是实测增益校准。CSV的raw_mV保留电极直流偏置；diag_reference_mV、fast_reference_mV为当前项目定点C++滤波器对完整原始记录从零状态重放的输出。重放结果与保存的板上末4秒输出逐码比对，偏差必须为0才导出。

保真/快速是同一输入的两条处理结果，不能算作两份独立原始样本，也不是人工标注的无噪声真值。输出与输入按处理时刻对应，没有对齐补偿；名义延迟分别174点/15点（348/30 ms），IIR部分另有随频率变化的相位响应。不能未经延迟处理就拿raw与diag逐点当作同一心电事件的监督配对。

优选规则：排除最前2秒与最后0.5秒，在其间按0.5秒步进评估连续10秒窗，比较原始49～51Hz、45～150Hz能量比例、滤波后慢漂移比例、反向异常偏移与削顶；选择工程评分最低的一个，并查看波形图核实。反向偏移指标是针对本次记录中短时运动干扰的启发式筛选，不是临床波形判定。此规则只用于本次记录内选段，未经过临床信号质量标准验证。保留全部候选评分，未拼接、删改或合成心拍。波形幅度没有归一化。

标称时间轴按500 Hz计算；此前内部时钟实测约499.46 Hz，本次没有独立时间戳，不能把标称时长当作精确物理时长。

## 模型训练注意

无疾病、心律或逐拍专家标签，不应标为“健康/正常心律”的已标注数据。只有一个受测者和两段短记录，适合作为自有硬件适配、回放及去噪探索，不能代表独立临床验证集。完整记录、优选片段、两条滤波路径和重叠候选窗存在重复，切分训练/验证/测试时必须按受测者/采集会话分组，不能随机混分这些派生数据。
''',encoding='utf-8')
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256清单.json'}
    (ROOT/'SHA256清单.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(ROOT),sessions=sessions),ensure_ascii=False,indent=2))

if __name__=='__main__': main()

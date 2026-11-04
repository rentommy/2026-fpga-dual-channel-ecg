from pathlib import Path
import subprocess
import json

OUT=Path(__file__).resolve().parent
DOT=Path('D:/Graphviz/bin/dot.exe')

def q(s):return json.dumps(s,ensure_ascii=False)

def system(lang):
 zh=lang=='zh'
 def tr(a,b):return a if zh else b
 nodes={
 'electrodes':('ext',tr('电极与模拟输入\n通道1 / 通道2（分别验证）','Electrodes / analog inputs\nCH1 / CH2 tested separately')),
 'adc':('ext',tr('自主采集板：ADS1292\n24位；配置500 Hz；电池供电\nRLD / START / RESET','Custom ADS1292 board\n24-bit; configured 500 samples/s\nBattery power; RLD / START / RESET')),
 'isolation':('ext',tr('数字隔离接口：ISO7763\n5路主机输出 + 2路返回\n采集侧 / PYNQ侧隔离边界','ISO7763 digital isolation\n5 host outputs + 2 return signals\nAcquisition / PYNQ isolation boundary')),
 'spi':('pl',tr('PL：SPI主机与DRDY触发读取\n状态字校验 / FIFO / 错误计数','PL: SPI master and DRDY-triggered reads\nFrame validation / FIFO / error counters')),
 'raw':('mem',tr('PS / DDR：原始采样缓冲\n两个输入；8槽位滤波输入组织\n原始样点时间基准','PS / DDR: raw-sample buffers\nTwo inputs; 8-slot filter input layout\nSource-sample time base')),
 'filter':('pl',tr('PL：共享基线处理\n温和高通 + 320点滑动平均\n单DSP时分复用；每通道状态','PL: shared baseline processing\nMild high-pass + 320-sample moving average\nOne time-multiplexed DSP; per-channel state')),
 'fast':('pl',tr('实时路径\nD=0；减去基线\n50 Hz陷波 + 31抽头FIR\n脉冲峰值偏移15点 / 30 ms','Real-time path\nD=0; baseline subtraction\n50 Hz notch + 31-tap FIR\nImpulse-peak offset: 15 samples / 30 ms')),
 'diag':('pl',tr('保真路径\nD=159；减去基线\n50 Hz陷波 + 31抽头FIR\n脉冲峰值偏移174点 / 348 ms','Fidelity path\nD=159; baseline subtraction\n50 Hz notch + 31-tap FIR\nImpulse-peak offset: 174 samples / 348 ms')),
 'preprocess':('ps',tr('ARM：独立模型预处理\n0.5–40 Hz带通 / 50 Hz陷波\n重采样至256 Hz','ARM: independent model preprocessing\n0.5–40 Hz band-pass / 50 Hz notch\nResample to 256 Hz')),
 'rpeak':('ps',tr('ARM：R峰检测与心拍切分\n源样点位置 / 前后心拍间期','ARM: R-peak detection / beat segmentation\nSource positions / adjacent RR intervals')),
 'features':('ps',tr('模型输入\n205点标准化波形 + 有效掩码\n8维RR特征（按config归一化）','Model inputs\n205-point normalized waveform + valid mask\n8 RR features normalized using config')),
 'schedule':('ps',tr('ARM：逐层推理调度\nGroupNorm / 激活 / 残差\n独立进程与有界队列','ARM: per-layer inference scheduling\nGroupNorm / activations / residuals\nSeparate process; bounded queues')),
 'conv':('pl',tr('PL：共享FP32 Conv1d加速器\n承担全部12个卷积层\nDDR数据交换 / AXI-HP','PL: shared FP32 Conv1d accelerator\nExecutes all 12 convolution layers\nDDR transfers / AXI-HP')),
 'head':('ps',tr('ARM：池化 / 门控 / RR分支\n全连接分类与概率\nA, F, L, N, R, S, V, |','ARM: pooling / gating / RR branch\nFully connected classifier / probabilities\nA, F, L, N, R, S, V, |')),
 'quality':('ps',tr('ARM：信号质量门控\n平直 / 削顶 / 工频 / 噪声\n不合格心拍拒绝；故障清空','ARM: signal-quality gating\nFlat / clipped / mains / noisy inputs\nReject poor beats; clear stale fault output')),
 'hr':('ps',tr('ARM：RR与心率 / 状态管理\n质量合格时显示估算值\n演示性阈值提示','ARM: RR / heart rate / status\nDisplay estimates with valid quality\nDemonstration threshold alerts')),
 'events':('ps',tr('ARM：延后心拍标签\n按源样点和路径延迟映射\n约2–3秒后回填（另有计算开销）','ARM: delayed beat annotations\nMap source positions and path delays\nAbout 2–3 s wait plus processing')),
 'draw':('ps',tr('ARM：显示数据整理\n4秒窗口 / 当前通道两路径同增益\n波形列范围 / 标签 / 中文状态位图','ARM: display preparation\n4-s window / same gain for selected paths\nWaveform columns / labels / Chinese HUD')),
 'video_mem':('mem',tr('PL BRAM：双缓冲视频数据\n4组波形与标签（2输入×2路径）\n中文HUD；帧边界同时提交','PL BRAM: double-buffered video data\n4 waveform/label banks (2 inputs × 2 paths)\nHUD; atomic submission at frame boundary')),
 'compositor':('pl',tr('PL：640×480视频合成\nSW0单路 / 上实时+下保真\n波形、标签与状态同步换帧','PL: 640×480 video composition\nSW0: single / real-time above fidelity\nWaveform, labels and HUD switch together')),
 'encoder':('pl',tr('PL：rgb2dvi / HDMI OUT','PL: rgb2dvi / HDMI OUT')),
 'monitor':('ext',tr('显示器 / HDMI采集卡\n已观察波形更新约27–30次/秒','Monitor / HDMI capture device\nObserved waveform updates: ~27–30/s')),
 'ui':('ctrl',tr('SW0 / BTN0–BTN3\n双路径布局 / 通道 / 模式 / 冻结','SW0 / BTN0–BTN3\nDual-path view / channel / mode / freeze')),
 'control':('ps',tr('ARM / PYNQ控制与缓存管理\nAXI-Lite启动 / 状态 / ADC配置\nDDR输入flush；完成后invalidate','ARM / PYNQ control and cache management\nAXI-Lite start / status / ADC configuration\nFlush inputs; invalidate completed outputs')),
 'params':('mem',tr('DDR：权重 / config.json\nFP32权重；标签顺序；RR均值/标准差','DDR: weights / config.json\nFP32 parameters; class order; RR mean / std')),
 }
 colors={'pl':('#F0EBFF','#7759A6'),'ps':('#E8F2FF','#4779AB'),'mem':('#F2F4F7','#718096'),'ext':('#E7F5EE','#428568'),'ctrl':('#FFF1D8','#A77B32')}
 lines=['digraph ECG {','graph [rankdir=TB, compound=true, newrank=true, bgcolor="white", pad=0.28, nodesep=0.28, ranksep=0.48, splines=polyline, dpi=130, fontname="Microsoft YaHei", fontsize=20, labelloc=t, label='+q(tr('完整系统框图：双路径心电显示与PS–PL协同识别','Complete System: Dual-Path ECG Display and PS–PL Recognition'))+'];','node [shape=box, style="rounded,filled", fontname="Microsoft YaHei", fontsize=13, margin="0.16,0.12", penwidth=1.2];','edge [fontname="Microsoft YaHei", fontsize=10, color="#53657A", arrowsize=0.65];']
 def node(k):
  role,label=nodes[k];fill,line=colors[role]
  return f'{k} [label={q(label)}, fillcolor="{fill}", color="{line}"];'
 for k in ['electrodes','adc','isolation','monitor']:lines.append(node(k))
 lines+=['subgraph cluster_pynq {label='+q(tr('PYNQ-Z2 / AMD XC7Z020；PL处理时钟100 MHz','PYNQ-Z2 / AMD XC7Z020; PL processing clock 100 MHz'))+'; color="#8195AC"; penwidth=1.4; style=rounded;']
 for k in nodes:
  if k not in ['electrodes','adc','isolation','monitor']:lines.append(node(k))
 lines+=['{rank=same; filter; preprocess; quality;}','{rank=same; fast; diag; rpeak;}','{rank=same; features; hr;}','{rank=same; schedule; conv; params;}','{rank=same; head; events;}','{rank=same; draw; control; ui;}','}']
 def edge(a,b,label='',control=False,extra=''):
  attrs=[]
  if label:attrs.append('label='+q(label))
  if control:attrs+=['style=dashed','color="#AE8031"','constraint=false']
  if extra:attrs.append(extra)
  lines.append(f'{a} -> {b} ['+', '.join(attrs)+'];')
 edge('electrodes','adc',tr('模拟心电','Analog ECG'))
 edge('adc','isolation',tr('DOUT / DRDY','DOUT / DRDY'))
 edge('isolation','spi',tr('隔离后信号','Isolated signals'))
 edge('spi','raw',tr('AXI-Lite读取FIFO','AXI-Lite FIFO reads'))
 edge('raw','filter',tr('DDR / AXI-HP','DDR / AXI-HP'))
 edge('filter','fast');edge('filter','diag')
 edge('fast','draw',tr('滤波输出缓冲','Filtered output buffer'))
 edge('diag','draw',tr('滤波输出缓冲','Filtered output buffer'))
 edge('raw','preprocess',tr('原始数据独立分支','Independent raw-data branch'))
 edge('raw','quality',tr('原始幅值检查','Raw amplitude checks'))
 edge('preprocess','rpeak');edge('preprocess','quality',extra='constraint=false')
 edge('rpeak','features');edge('rpeak','hr')
 edge('features','schedule');edge('params','schedule',control=True)
 edge('schedule','conv',tr('逐层输入 / 结果','Per-layer inputs / outputs'),extra='dir=both')
 edge('schedule','head');edge('features','head',tr('RR旁路','RR branch'),extra='constraint=false')
 edge('head','events');edge('quality','events',tr('质量门控','Quality gate'),True)
 edge('quality','hr',tr('质量 / 故障状态','Quality / fault status'),True)
 edge('events','draw');edge('hr','draw',tr('心率 / 状态','Heart rate / status'))
 edge('draw','video_mem',tr('AXI-Lite写入非活动缓存','AXI-Lite writes to inactive buffer'))
 edge('video_mem','compositor');edge('compositor','encoder');edge('encoder','monitor',tr('HDMI','HDMI'))
 edge('ui','compositor',tr('SW0 / 布局选择','SW0 / view selection'),True)
 edge('ui','control',tr('通道 / 模式 / 冻结','Channel / mode / freeze'),True)
 edge('control','draw',tr('选择 / 冻结','Selection / freeze'),True)
 edge('control','spi',tr('配置 / START / RESET / RLD选择','Configure / START / RESET / RLD selection'),True)
 edge('spi','isolation',tr('CS / SCLK / DIN / START / RESET','CS / SCLK / DIN / START / RESET'),True)
 edge('isolation','adc',tr('隔离后控制','Isolated control'),True)
 edge('control','filter',tr('启动 / 状态','Start / status'),True)
 edge('control','conv',tr('寄存器调度','Register scheduling'),True)
 lines+=['legend [shape=plaintext, fontsize=11, label='+q(tr('实线：数据流    虚线：控制/状态\n蓝色：PS/ARM    紫色：PL硬件    灰色：内存\n30/348 ms为滤波峰值偏移，非端到端时延；两条显示路径来自同一选中输入。','Solid: data flow    Dashed: control/status\nBlue: PS/ARM    Purple: PL hardware    Gray: memory\n30/348 ms are filter peak offsets, not end-to-end latency. Both display paths use one selected input.'))+'];','monitor -> legend [style=invis];','}']
 return '\n'.join(lines)

def detail(lang):
 zh=lang=='zh'
 def tr(a,b):return a if zh else b
 return '''digraph Dual {
 graph [rankdir=LR, bgcolor="white", pad=0.3, nodesep=0.4, ranksep=0.5, dpi=150, fontname="Microsoft YaHei", fontsize=18, labelloc=t, label=%s];
 node [shape=box, style="rounded,filled", fillcolor="#F0EBFF", color="#7759A6", fontname="Microsoft YaHei", fontsize=13, margin="0.15,0.14"];
 edge [color="#53657A", arrowsize=0.7];
 input [label=%s,fillcolor="#E8F2FF"];
 shared [label=%s];
 rt [label=%s]; fidelity [label=%s];
 nf1 [label=%s]; nf2 [label=%s];
 out1 [label=%s,fillcolor="#E7F5EE"];out2 [label=%s,fillcolor="#FFF1D8"];
 input -> shared; shared -> rt; shared -> fidelity; rt -> nf1; fidelity -> nf2;nf1 -> out1;nf2 -> out2;
 note [shape=plaintext,label=%s,fontsize=11];
 out2 -> note [style=invis];
}''' % tuple(q(s) for s in [tr('双路径滤波细节（每个输入通道）','Dual-Path Filtering Detail (per input channel)'),tr('原始采样\n500 Hz','Raw samples\n500 samples/s'),tr('共享前级与历史状态\n温和高通\n320点滑动平均基线','Shared front end and history\nMild high-pass\n320-sample baseline average'),tr('抽头D=0\n减去同一基线估计','Tap D=0\nSubtract shared baseline'),tr('抽头D=159\n减去同一基线估计','Tap D=159\nSubtract shared baseline'),tr('50 Hz陷波\n31抽头FIR低通','50 Hz notch\n31-tap FIR low-pass'),tr('50 Hz陷波\n31抽头FIR低通','50 Hz notch\n31-tap FIR low-pass'),tr('实时输出\n峰值偏移15点 / 30 ms','Real-time output\nPeak offset: 15 samples / 30 ms'),tr('保真输出\n峰值偏移174点 / 348 ms','Fidelity output\nPeak offset: 174 samples / 348 ms'),tr('单DSP时分复用计算，两路径保留独立状态。\n图表示逻辑数据流，不表示两套完全独立流水线。','One time-multiplexed DSP; separate path state.\nLogical data flow, not two fully independent pipelines.')])

for lang in ['zh','en']:
 for stem,text in [('system_diagram',system(lang)),('dual_path_detail',detail(lang))]:
  path=OUT/f'{stem}_{lang}.dot';path.write_text(text,encoding='utf8')
  for fmt in ['svg','png']:
   result=subprocess.run([str(DOT),f'-T{fmt}',str(path),'-o',str(path.with_suffix('.'+fmt))],capture_output=True,text=True)
   if result.returncode:raise RuntimeError(result.stderr)
   if result.stderr:print(result.stderr)
for lang in ['zh','en']:
 p=OUT/f'poster_text_{lang}.md';(OUT/f'poster_text_{lang}.txt').write_text(p.read_text(encoding='utf8'),encoding='utf8')
print('Generated bilingual texts and editable DOT/SVG plus PNG diagrams in',OUT)

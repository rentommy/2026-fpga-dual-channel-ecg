from pathlib import Path
import subprocess,html

OUT=Path(__file__).resolve().parent
def esc(s):return html.escape(s).replace('\n','<BR/>')
def table(title,rows,color):
 return '<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="10" COLOR="black"><TR><TD COLSPAN="2"><FONT COLOR="#AD1515"><B>'+esc(title)+'</B></FONT></TD></TR>'+''.join(rows)+'</TABLE>'
def cell(text,color,port='',width=135):
 return '<TD BORDER="1" BGCOLOR="'+color+'" WIDTH="'+str(width)+'"'+(' PORT="'+port+'"' if port else '')+'>'+esc(text)+'</TD>'

for lang in ['zh','en']:
 zh=lang=='zh'
 def tr(a,b):return a if zh else b
 adc=table(tr('自主心电采集板','Custom ECG Acquisition Board'),[
  '<TR><TD COLSPAN="2" BORDER="1" PORT="adc" BGCOLOR="#D59891">ADS1292<BR/>'+esc(tr('双通道 / 24位 / 500 Hz','2 channels / 24-bit / 500 samples/s'))+'</TD></TR>',
  '<TR>'+cell(tr('电池供电','Battery power'),'#FCF7DC',width=110)+cell(tr('采样时钟','Sampling clock'),'#FCF7DC',width=110)+'</TR>'
 ],'')
 pynq=table('PYNQ-Z2 / XC7Z020',[
  '<TR>'+cell(tr('PL：FPGA逻辑','PL: FPGA Logic'),'#E1EAF6',width=190)+cell(tr('PS：ARM处理器','PS: ARM Processor'),'#FFF0CD',width=190)+'</TR>',
  '<TR>'+cell(tr('SPI采集与FIFO','SPI Acquisition / FIFO'),'#E1EAF6','spi',190)+cell(tr('数据流与采集控制','Data Flow / Acquisition Control'),'#FFF0CD','control',190)+'</TR>',
  '<TR>'+cell(tr('双路径数字滤波\n实时30 ms / 保真348 ms','Dual-Path Digital Filtering\nReal-time 30 ms / Fidelity 348 ms'),'#D5E8F8','filter',190)+cell(tr('R峰 / RR特征 / 心率\n归一化与分类控制','R Peaks / RR / Heart Rate\nNormalization / Classifier Control'),'#FFF0CD','rr',190)+'</TR>',
  '<TR>'+cell(tr('FP32卷积加速\n全部12层Conv1d','FP32 Convolution Accelerator\nAll 12 Conv1d Layers'),'#D4C7E8','conv',190)+cell(tr('波形与延时标签整理\n中文状态与按键交互','Waveform / Delayed Labels\nStatus / User Interaction'),'#FFF0CD','display',190)+'</TR>',
  '<TR><TD COLSPAN="2" BORDER="1" PORT="video" BGCOLOR="#D5E8F8">'+esc(tr('PL视频合成 / 双缓冲 / HDMI编码','PL Video Composition / Double Buffering / HDMI Encoding'))+'</TD></TR>',
  '<TR><TD COLSPAN="2" BORDER="1" BGCOLOR="#BDD19E">'+esc(tr('AXI互连与DDR共享内存','AXI Interconnect / Shared DDR Memory'))+'</TD></TR>'
 ],'')
 source='''digraph Simple {
 graph [rankdir=LR, bgcolor="white", pad="0.18", nodesep=0.35, ranksep=0.55, dpi=160, splines=polyline, fontname="Microsoft YaHei", labelloc=b, fontsize=12, label="%s"];
 node [shape=plain, fontname="Microsoft YaHei", fontsize=15];
 edge [fontname="Microsoft YaHei", fontsize=12, color="black", arrowsize=0.75, penwidth=1.2];
 lead [label="%s"];
 adc [label=<%s>];
 iso [label=<<TABLE BORDER="1" CELLBORDER="0" CELLPADDING="12" BGCOLOR="#F3B16A"><TR><TD>%s<BR/>ISO7763</TD></TR></TABLE>>];
 pynq [label=<%s>];
 hdmi [label=<<TABLE BORDER="1" CELLBORDER="0" CELLPADDING="12"><TR><TD BGCOLOR="#BDD19E">HDMI OUT</TD></TR><TR><TD>%s</TD></TR></TABLE>>];
 lead -> adc:adc:w;
 adc:adc:e -> iso [dir=both,label="%s"];
 iso -> pynq:spi:w [dir=both,label="%s"];
 pynq:video:e -> hdmi [label="%s"];
}'''%(tr('30/348 ms为滤波脉冲峰值偏移，非整机端到端时延。SW0选择单路或上下双路径显示。','30/348 ms: filter impulse-peak offsets, not end-to-end latency. SW0 selects single or stacked dual-path view.'),tr('电极输入\nCH1 / CH2','Electrode Inputs\nCH1 / CH2'),adc,esc(tr('数字隔离','Digital Isolation')),pynq,esc(tr('波形 / 心率\n逐拍识别标签','Waveform / Heart Rate\nBeat Labels')),tr('SPI信号','SPI Signals'),tr('SPI / DRDY','SPI / DRDY'),tr('视频输出','Video Output'))
 p=OUT/f'system_diagram_simple_{lang}.dot';p.write_text(source,encoding='utf8')
 for fmt in ['svg','png']:
  subprocess.run(['D:/Graphviz/bin/dot.exe','-T'+fmt,str(p),'-o',str(p.with_suffix('.'+fmt))],check=True)
print('Simple bilingual block diagrams ready')

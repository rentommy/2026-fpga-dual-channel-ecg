import fs from 'node:fs/promises';
import { FileBlob, PresentationFile } from 'file:///C:/Users/rentommy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';

const base='D:/ecg_fpga/海报';
const raw=await fs.readFile('D:/ecg_fpga/report/inference_20261104/classified_ecg.png');
const img=raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength);
const copies={
 zh:{title:'基于 FPGA 的双通道心电监测与辅助识别系统', people:'团队：任家霖  程硕  李一博     学校：[待填写]', headings:['项目简介','系统设计','测试结果与展望'],
 intro:'面向嵌入式实时心电展示，系统结合自主设计的 ADS1292 采集板与 PYNQ-Z2 平台，实现采集、滤波、逐拍识别和 HDMI 显示。\n\n采集板经隔离接口连接开发板，支持两个输入通道。24 位采样数据通过 SPI 传输，当前采样率为 500 Hz。',
 intro2:'展示功能\n• 滚动波形与心率，按键切换通道和模式\n• 逐拍分类延时回填，支持冻结画面\n• 信号质量检查及演示性预警',
 arch:'ADS1292 采集板  →  隔离 SPI  →  PYNQ-Z2\n\nPL：双路径数字滤波与 50 Hz 陷波\nPL：12 层 FP32 卷积加速\nPS / ARM：R 峰检测、RR 特征、归一化及分类\nHDMI：实时波形、心率与延时识别标签',
 note:'处理器负责 R 峰、心率和分类调度；卷积与滤波由可编程逻辑承担。识别依赖后续心拍信息，标签通常在心拍后约 2–3 秒显示。',
 result:'实测进展\n• 两个通道分别获得人体心电，现场确认波形、心率、中文及按键正常。\n• 49 个真实记录心拍的板端分类与 PyTorch 参考结果 49/49 一致；这是部署一致性，不是临床准确率。\n• 板端单拍完整推理平均约 120 ms（特定测试条件）。',
 cap:'两次独立采集的真实心电及回放识别结果',
 limit:'后续：完成连续采集稳定性、断流恢复及更多标注数据验证。系统为竞赛原型，不用于临床诊断。'},
 en:{title:'FPGA-Based Dual-Channel ECG Monitoring and Assisted Classification', people:'Team: Jialin Ren, Shuo Cheng, Yibo Li     Institution: [to be added]',headings:['INTRODUCTION','SYSTEM DESIGN','RESULTS & NEXT STEPS'],
 intro:'A custom ADS1292 acquisition board and PYNQ-Z2 platform form an embedded ECG prototype for acquisition, filtering, beat classification and HDMI display.\n\nThe isolated SPI interface transfers 24-bit samples from two input channels at a configured 500 samples/s.',
 intro2:'Demonstration features\n• Scrolling ECG and heart rate; buttons select channel and mode\n• Delayed beat labels and a freeze control\n• Signal-quality checks and demonstration alerts',
 arch:'ADS1292 board  →  isolated SPI  →  PYNQ-Z2\n\nPL: dual-path filtering and 50 Hz notch\nPL: 12 FP32 convolution layers\nPS / ARM: R-peak detection, RR features and classifier\nHDMI: waveform, heart rate and delayed beat labels',
 note:'The ARM handles beat detection, heart rate and inference control. The PL accelerates filtering and convolution. Labels normally appear about 2–3 s after a beat because later beat information is required.',
 result:'Observed results\n• Human ECG was recorded separately on both channels. Waveform, heart rate, Chinese UI and buttons were checked on the live system.\n• FPGA-assisted outputs agreed with PyTorch on 49/49 recorded beats. This measures implementation agreement, not clinical accuracy.\n• Mean full inference time was about 120 ms per beat in one board test.',
 cap:'Recorded ECG and replayed classifications from two separate acquisitions (original plot labels in Chinese)',
 limit:'Next: verify sustained acquisition, recovery after interruptions and performance on additional labelled data. Research prototype; not for clinical diagnosis.'}
};
function addText(slide,text,x,y,w,h,size,opt={}){
 const s=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:opt.fill||'none',line:{fill:'none',width:0}});
 s.text=text; s.text.style={fontFamily:opt.font||'Microsoft YaHei',fontSize:size,color:opt.color||'#222222',bold:!!opt.bold,verticalAlignment:'middle',wrap:true}; return s;
}
for (const [lang,c] of Object.entries(copies)) {
 const p=await PresentationFile.importPptx(await FileBlob.load('D:/ecg_fpga/海报/_build/template_clean.pptx'));
 const s=p.slides.items[0];
 const info=await p.inspect({select:'$.slides[*].elements[*]',include:['id','kind','position']});
 const logo=info.records.find(x=>x.kind==='image' && x.position.left>850 && x.position.left<900 && x.position.top<120);
 p.delete(info.records.filter(x=>x.id!==logo?.id).map(x=>x.id));
 if(logo){const l=p.resolve(logo.id);l.position={left:1090,top:8,width:157,height:88};}
 addText(s,lang==='en'?'Dual-Channel ECG Monitoring with FPGA Acceleration':c.title,28,24,1030,43,lang==='zh'?28:25,{bold:true,font:lang==='zh'?'Microsoft YaHei':'Times New Roman'});
 addText(s,c.people,30,70,1000,25,15,{font:lang==='zh'?'Microsoft YaHei':'Times New Roman'});
 const col=[30,447,864], wid=385;
 for(let i=0;i<3;i++)addText(s,c.headings[i],col[i],115,wid,35,18,{fill:'#303030',color:'#FFFFFF',bold:true,font:lang==='zh'?'Microsoft YaHei':'Calibri'});
 addText(s,c.intro,30,162,wid,190,17);
 addText(s,c.intro2,30,365,wid,160,16);
 addText(s,lang==='zh'?'平台：AMD XC7Z020 / PYNQ-Z2':'Platform: AMD XC7Z020 / PYNQ-Z2',30,575,wid,55,17,{bold:true});
 addText(s,c.arch,447,164,wid,216,17,{bold:true});
 addText(s,c.note,447,397,wid,150,16);
 addText(s,lang==='zh'?'硬件与软件协同处理':'Hardware and software working together',447,575,wid,50,16,{bold:true});
 addText(s,c.result,864,158,wid,238,15.5);
 s.images.add({blob:img,contentType:'image/png',alt:'Real ECG records and replay classification results',fit:'contain',position:{left:864,top:399,width:385,height:218}});
 addText(s,c.cap,864,618,wid,33,11.5);
 addText(s,c.limit,864,653,wid,58,12.5);
 const output=`${base}/${lang==='zh'?'项目海报_中文版':'Project_Poster_English'}.pptx`;
 await (await PresentationFile.exportPptx(p)).save(output);
 const png=await p.export({slide:s,format:'png',scale:1.5});
 await fs.writeFile(`${base}/_build/${lang}.png`,new Uint8Array(await png.arrayBuffer()));
 console.log(output);
}

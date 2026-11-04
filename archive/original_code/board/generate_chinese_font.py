"""Generate only the 16x16 glyphs needed by the HDMI UI, not a full font."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
font = ImageFont.truetype('C:/Windows/Fonts/simhei.ttf', 16)
texts = {
    'title_diag_live': '心电波形  通道1  保真  实时  自动增益',
    'title_fast_hold': '心电波形  通道2  快速  冻结  自动增益',
    'subtitle_demo': '演示波形 / 500点每秒 / 4秒窗口',
    'subtitle_adc': '采集信号 / 500点每秒 / 4秒窗口',
    'subtitle_test': '内部测试信号 / 500点每秒 / 4秒窗口',
    'subtitle_error': '无采集数据 / 请检查连接',
    'footer': '键0通道1  键1通道2  键2模式  键3冻结',
    'model_hint': '逐拍识别：延后回填   问号表示等待',
}
chars = sorted(set(''.join(texts.values())))
lines = ['// Generated 16x16 monochrome UI glyphs (BMP codepoints).',
         'function automatic [15:0] chinese_font_row(input [15:0] ch,input [3:0] row);',
         'reg [255:0] glyph;', 'begin', 'case(ch)']
for ch in chars:
    tile = Image.new('L', (16, 16), 0)
    d = ImageDraw.Draw(tile)
    box = d.textbbox((0, 0), ch, font=font)
    d.text(((16-(box[2]-box[0]))//2-box[0], (16-(box[3]-box[1]))//2-box[1]), ch, font=font, fill=255)
    bits = ''.join('1' if tile.getpixel((x, y)) >= 100 else '0' for y in range(16) for x in range(16))
    lines.append(f"16'h{ord(ch):04x}:glyph=256'h{int(bits,2):064x}; // {ch}")
lines += ["default:glyph=256'd0;", 'endcase', 'chinese_font_row=glyph[(15-row)*16+:16];', 'end', 'endfunction']
(root/'src/rtl/ecg_chinese_font.vh').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def text_function(name, text):
    return '\n'.join([f'function automatic [15:0] {name}(input integer index);',
       'begin', f'{name}=16\'h0020;', 'case(index)'] +
       [f"{i}:{name}=16'h{ord(ch):04x};" for i,ch in enumerate(text) if ch != ' '] +
       ['endcase', 'end', 'endfunction'])

functions = '\n\n'.join(text_function(name,text) for name,text in texts.items())
functions += '''
function automatic [15:0] heading(input integer index,input [2:0] sel);
begin
heading=title_diag_live(index);
case(index)
8:heading=sel[0]?16'h0032:16'h0031;
11:heading=sel[1]?16'h5feb:16'h4fdd;
12:heading=sel[1]?16'h901f:16'h771f;
15:heading=sel[2]?16'h51bb:16'h5b9e;
16:heading=sel[2]?16'h7ed3:16'h65f6;
endcase
end
endfunction
function automatic [15:0] subtitle(input integer index,input [1:0] flags);
begin
if(flags==3) subtitle=subtitle_test(index);
else if(flags[0]) subtitle=subtitle_demo(index);
else if(flags[1]) subtitle=subtitle_error(index);
else subtitle=subtitle_adc(index);
end
endfunction
'''
(root/'src/rtl/ecg_chinese_labels.vh').write_text(functions,encoding='utf-8')
preview=Image.new('RGB',(640,220),'#070d17'); draw=ImageDraw.Draw(preview)
for i,(name,text) in enumerate(texts.items()):
    draw.text((16,8+i*29),text,font=font,fill='#eaf2ff')
preview.save(root/'board/scope/chinese_font_preview.png')
print(f'Generated {len(chars)} glyphs; longest label {max(map(len,texts.values()))} cells')

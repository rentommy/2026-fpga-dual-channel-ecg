"""Generate the small Chinese glyph subset needed by the live status row."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parent
texts=['心率 次/分 信号 良好 较差 收集中 待确认 分析延迟 分析故障 观察中 低于下限 超过上限 连续非N分类 检查电极 无有效心拍 采集故障 无数据 --0123456789']
font=ImageFont.truetype('C:/Windows/Fonts/simhei.ttf',16)
glyphs={}
for ch in sorted(set(''.join(texts))):
    image=Image.new('L',(16,16));draw=ImageDraw.Draw(image);box=draw.textbbox((0,0),ch,font=font)
    draw.text(((16-(box[2]-box[0]))//2-box[0],(16-(box[3]-box[1]))//2-box[1]),ch,font=font,fill=255)
    a=np.asarray(image)>=100
    glyphs[str(ord(ch))]=np.array([sum(int(a[y,x])<<(15-y) for y in range(16)) for x in range(16)],np.uint32)
np.savez(root/'hud_glyphs.npz',**glyphs)
print('HUD_GLYPHS',len(glyphs))

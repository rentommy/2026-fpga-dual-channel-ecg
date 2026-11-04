import numpy as np

class HUD:
    def __init__(self,folder):self.glyphs=dict(np.load(folder/'hud_glyphs.npz',allow_pickle=False))
    def render(self,state):
        rate='--' if state['bpm'] is None else str(round(state['bpm']))
        q={'GOOD':'良好','POOR':'较差','WARMUP':'收集中','UNCERTAIN':'待确认','STALE':'分析延迟','ERROR':'分析故障'}[state['quality']]
        if state['state']=='ACQUISITION_ERROR':q='无数据'
        status={'OBSERVE':'观察中','RATE_LOW':'低于下限','RATE_HIGH':'超过上限','MODEL_REVIEW':'连续非N分类',
                'SIGNAL_BAD':'检查电极','WARMUP':'收集中','NO_BEATS':'无有效心拍','STALE':'分析延迟','ERROR':'分析故障','ACQUISITION_ERROR':'采集故障'}[state['state']]
        colour=1 if state['state']=='OBSERVE' else (3 if state['state'] in ['RATE_LOW','RATE_HIGH','MODEL_REVIEW','ERROR','ACQUISITION_ERROR'] else 2)
        line=f'心率 {rate}次/分  信号{q}  {status}'
        out=np.zeros(640,np.uint32)
        for j,ch in enumerate(line[:38]):out[16+j*16:32+j*16]=self.glyphs.get(str(ord(ch)),self.glyphs[str(ord(' '))])|(colour<<16)
        return out

"""Conservative engineering signal gates, heart-rate estimates and sustained alerts."""
import json
from pathlib import Path
import numpy as np

MV_PER_CODE=2.42/6/(2**23-1)*1000

def assess_quality(raw,filtered):
    raw=np.asarray(raw,dtype=float);y=np.asarray(filtered,dtype=float)
    if len(raw)<1000 or len(y)<512:return dict(state='WARMUP',reason='COLLECTING')
    raw=raw[-2000:];y=y[-1024:]
    span=float(np.percentile(y,99)-np.percentile(y,1))
    raw_span=float(np.percentile(raw,99)-np.percentile(raw,1))*MV_PER_CODE
    clipped=float(np.mean(np.abs(raw)>=.98*(2**23-1)))
    x=raw-raw.mean();power=np.abs(np.fft.rfft(x*np.hanning(len(x))))**2
    f=np.fft.rfftfreq(len(x),1/500)
    denominator=max(float(power[(f>=1)&(f<=100)].sum()),1e-30)
    mains=float(power[(f>=49)&(f<=51)].sum()/denominator)
    hf=float(power[(f>=35)&(f<=100)].sum()/denominator)
    fy=np.fft.rfftfreq(len(y),1/256);py=np.abs(np.fft.rfft((y-y.mean())*np.hanning(len(y))))**2
    baseline=float(py[(fy>=.25)&(fy<2)].sum()/max(float(py[(fy>=.25)&(fy<=40)].sum()),1e-30))
    reason='GOOD'
    if clipped>.001:reason='CLIPPED'
    elif raw_span<.015 or span<.025:reason='FLAT'
    elif mains>.90:reason='MAINS'
    elif hf>.85:reason='NOISY'
    elif span>8 or (baseline>.75 and span>1.5):reason='MOTION'
    return dict(state='GOOD' if reason=='GOOD' else 'POOR',reason=reason,
                span_mv=span,raw_span_mv=raw_span,clipped_fraction=clipped,
                mains_fraction=mains,high_frequency_fraction=hf,baseline_fraction=baseline)

def measure_monitor(raw,filtered,times):
    # End 0.5 s before the snapshot edge to avoid zero-phase filter edge transients.
    q=assess_quality(raw[-2250:-250],filtered[-1152:-128])
    end=len(raw)/500
    recent=np.asarray(times)[np.asarray(times)>=end-8]
    rr=np.diff(recent)
    bpm=None;age=None
    if len(recent):age=float(end-recent[-1])
    if len(rr)>=3 and np.all((rr[-5:]>=.25)&(rr[-5:]<=2.5)):
        median=float(np.median(rr[-5:]))
        if age<=max(3,2.5*median):bpm=60/median
    return dict(quality=q,bpm=bpm,rr_seconds=rr[-5:].tolist(),last_peak_age_seconds=age)

class MonitorState:
    def __init__(self,config):
        self.config=dict(config);self.reset()
    def reset(self):
        self.measurement=None;self.measured_at=None;self.good_since=None
        self.bpm=None;self.rate_candidate=None;self.rate_since=None;self.rate_alert=None;self.recovery_since=None
        self.model_count=0;self.model_until=-1;self.last_beat=-1;self.last_label=None
    def ingest(self,measurement,at,beats):
        if self.measured_at is not None and at-self.measured_at>self.config['max_result_age_seconds']:self.reset()
        self.measurement=measurement;self.measured_at=at
        good=measurement['quality']['state']=='GOOD' and measurement['bpm'] is not None
        if not good:
            self.good_since=None;self.bpm=None;self.rate_candidate=None;self.rate_since=None
            self.rate_alert=None;self.recovery_since=None;self.model_count=0;self.model_until=-1
            return
        if self.good_since is None:self.good_since=at
        if at-self.good_since<self.config['quality_recovery_seconds']:return
        self.bpm=measurement['bpm'] if self.bpm is None else .75*self.bpm+.25*measurement['bpm']
        condition='RATE_LOW' if self.bpm<self.config['rate_low_bpm'] else ('RATE_HIGH' if self.bpm>self.config['rate_high_bpm'] else None)
        if condition:
            self.recovery_since=None
            if condition!=self.rate_candidate:self.rate_candidate=condition;self.rate_since=at
            if at-self.rate_since>=self.config['rate_hold_seconds']:self.rate_alert=condition
        else:
            self.rate_candidate=None;self.rate_since=None
            if self.recovery_since is None:self.recovery_since=at
            if at-self.recovery_since>=self.config['recovery_seconds']:self.rate_alert=None
        for beat in beats:
            if beat['source_sample']<=self.last_beat:continue
            self.last_beat=beat['source_sample'];self.last_label=beat['label']
            qualified=(beat.get('quality',{}).get('state')=='GOOD' and
                       beat['confidence']>=self.config['model_probability'] and beat['label'] in 'AFLRSV')
            self.model_count=self.model_count+1 if qualified else 0
            if self.model_count>=self.config['model_consecutive_beats']:self.model_until=at+self.config['model_alert_seconds']
    def view(self,now,error=None,instant_bad=False):
        if error:return dict(bpm=None,quality='ERROR',state='ERROR',reason=error)
        if instant_bad:return dict(bpm=None,quality='POOR',state='SIGNAL_BAD',reason='FLAT_OR_CLIPPED')
        if self.measurement is None:return dict(bpm=None,quality='WARMUP',state='WARMUP',reason='COLLECTING')
        if now-self.measured_at>self.config['max_result_age_seconds']:
            return dict(bpm=None,quality='STALE',state='STALE',reason='ANALYSIS_DELAY')
        q=self.measurement['quality']
        if q['state']!='GOOD':return dict(bpm=None,quality=q['state'],state='SIGNAL_BAD',reason=q['reason'])
        if self.measurement['bpm'] is None:return dict(bpm=None,quality='UNCERTAIN',state='NO_BEATS',reason='NO_RELIABLE_RR')
        if self.bpm is None:return dict(bpm=None,quality='WARMUP',state='WARMUP',reason='RECOVERING')
        return dict(bpm=round(float(self.bpm),1),quality='GOOD',state=self.rate_alert or ('MODEL_REVIEW' if now<self.model_until else 'OBSERVE'),
                    reason='SUSTAINED_THRESHOLD' if self.rate_alert else ('REPEATED_NON_N' if now<self.model_until else 'TRACKING'),
                    last_model_label=self.last_label,consecutive_model_beats=self.model_count)

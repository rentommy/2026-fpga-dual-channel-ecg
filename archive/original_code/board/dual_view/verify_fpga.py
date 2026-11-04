"""Replay previously exported beats; compare FPGA convolution with torch logits."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import argparse,json,time
from pathlib import Path
import numpy as np
from pynq import Overlay
from ecg_model import BeatModel,FPGAConv

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='fpga_replay_results.json');args=parser.parse_args()
    root=Path(__file__).resolve().parent
    overlay=Overlay(str(root/'overlay/ecg_inference.bit'))
    model=BeatModel(root/'model');conv=FPGAConv(overlay.ecg_conv_0,model.w);model.conv_engine=conv
    inputs=np.load(root/'model/replay_inputs.npz');reference=json.loads((root/'model/reference_results.json').read_text())
    results=[]
    try:
        for i,(x,rr,expected) in enumerate(zip(inputs['x'],inputs['rr'],inputs['logits'])):
            begin=time.monotonic();calls=conv.calls;seconds=conv.seconds
            logits=model(x,rr);p=np.exp(logits-logits.max());p/=p.sum()
            error=float(np.max(np.abs(logits-expected)))
            item=dict(index=i,label=reference['classes'][int(logits.argmax())],reference_label=reference['classes'][int(expected.argmax())],
                      confidence=float(p.max()),max_logit_error=error,wall_seconds=time.monotonic()-begin,
                      fpga_conv_seconds=conv.seconds-seconds,fpga_conv_calls=conv.calls-calls,
                      recording=reference['records'][i]['recording'],anchor_nominal_s=reference['records'][i]['anchor_nominal_s'])
            results.append(item);print(json.dumps(item),flush=True)
            assert error<5e-4 and logits.argmax()==expected.argmax(),item
        cpu=BeatModel(root/'model');cpu_seconds=[]
        for x,rr in zip(inputs['x'][:3],inputs['rr'][:3]):
            begin=time.monotonic();cpu(x,rr);cpu_seconds.append(time.monotonic()-begin)
        summary=dict(passed=True,beats=len(results),max_logit_error=max(v['max_logit_error'] for v in results),
                     mean_wall_seconds=float(np.mean([v['wall_seconds'] for v in results])),
                     max_wall_seconds=max(v['wall_seconds'] for v in results),
                     total_fpga_conv_calls=conv.calls,results=results,
                     cpu_baseline_beats=len(cpu_seconds),cpu_baseline_mean_seconds=float(np.mean(cpu_seconds)),
                     first3_pipeline_speedup=float(np.mean(cpu_seconds)/np.mean([v['wall_seconds'] for v in results[:3]])),
                     note='Numerical deployment test on unlabelled self-recorded ECG; not classification accuracy')
        Path(args.output).write_text(json.dumps(summary,indent=2));print('FPGA_REPLAY_PASS',json.dumps({k:v for k,v in summary.items() if k!='results'}),flush=True)
    finally:conv.close()

if __name__=='__main__':main()

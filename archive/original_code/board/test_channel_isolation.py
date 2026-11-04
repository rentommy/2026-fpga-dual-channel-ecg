"""Real-board distinct-channel replay, one-hot isolation, and reset/chunk checks."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--vectors', type=Path, default=Path(__file__).parent/'channel_test')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'channel_test_results')
    args = parser.parse_args()
    from pynq import Overlay, allocate
    x = np.fromfile(args.vectors/'distinct_input.bin', dtype='<i4').reshape(-1,8)
    expected = np.fromfile(args.vectors/'distinct_expected.bin',dtype='<i4').reshape(-1,8,2)
    assert x.shape == (4096,8) and expected.shape == (4096,8,2)
    args.output.mkdir(parents=True,exist_ok=True)
    overlay = Overlay(str(args.overlay))
    ip = overlay.ecg_filter_0
    ib = allocate(shape=(4096,8),dtype=np.int32)
    ob = allocate(shape=(4096,8,2),dtype=np.int32)
    safe_to_free = True

    def replay(data, pattern):
        nonlocal safe_to_free
        result = np.empty((len(data),8,2),dtype=np.int32)
        start = 0
        index = 0
        while start < len(data):
            count = min(pattern[index % len(pattern)],len(data)-start)
            ib[:count] = data[start:start+count]
            ob[:] = 0
            ib.flush(); ob.flush()
            for offset,address in [(0x10,int(ib.physical_address)),(0x1c,int(ob.physical_address))]:
                ip.write(offset,address & 0xffffffff); ip.write(offset+4,address>>32)
            ip.write(0x28,count); ip.write(0x30,int(start==0))
            safe_to_free = False
            before = time.monotonic(); ip.write(0,1)
            while not (ip.read(0)&2):
                if time.monotonic()-before > 5: raise TimeoutError('IP completion timeout; reboot before reuse')
                time.sleep(0.0001)
            safe_to_free = True
            ob.invalidate(); result[start:start+count] = ob[:count]
            start += count; index += 1
        return result

    checks = []
    def check(name, condition, **details):
        checks.append({'name':name,'passed':bool(condition),**details})
        print(json.dumps(checks[-1]),flush=True)
        (args.output/'checks.json').write_text(json.dumps(checks,indent=2))
        if not condition: raise AssertionError(name)

    try:
        mixed = replay(x,[4096])
        np.save(args.output/'distinct_output.npy',mixed)
        diff = np.abs(mixed.astype(np.int64)-expected)
        check('distinct_inputs_vs_host_core',np.array_equal(mixed,expected),max_error_codes=int(diff.max()))
        check('zero_sentinel_channel7',not np.any(mixed[:,7,:]))
        irregular = replay(x,[1,7,319,320,321,500,997])
        check('irregular_chunks_bit_exact',np.array_equal(mixed,irregular))
        for ch in range(8):
            one = np.zeros_like(x)
            one[:,ch] = x[:,ch] if ch != 7 else x[:,5]
            isolated = replay(one,[317])
            others = [i for i in range(8) if i != ch]
            check('one_hot_inactive_zero_ch'+str(ch),not np.any(isolated[:,others,:]))
            if ch != 7:
                check('one_hot_active_matches_mixed_ch'+str(ch),np.array_equal(isolated[:,ch,:],mixed[:,ch,:]))
            else:
                # ch7 and ch5 have identical delay configuration.
                check('one_hot_ch7_matches_ch5',np.array_equal(isolated[:,7,:],mixed[:,5,:]))
        check('reset_after_other_records',np.array_equal(replay(x,[500]),mixed))
        summary = {'passed':True,'samples':len(x),'channels':8,'paths':2,
                   'checks':checks,'bit_sha256':hashlib.sha256(args.overlay.read_bytes()).hexdigest(),
                   'scope':'Bounded deterministic vectors; exact host-core comparison, all eight one-hot isolation cases, irregular chunks, record reset. Not full-scale overflow or live ADC validation.'}
        (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
        print('CHANNEL_TEST_PASS',len(checks),flush=True)
    finally:
        if safe_to_free:
            ib.freebuffer(); ob.freebuffer()


if __name__ == '__main__':
    main()

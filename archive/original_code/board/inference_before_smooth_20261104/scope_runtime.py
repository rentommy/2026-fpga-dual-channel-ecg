"""ECG HDMI scope. Default demo never sends ADC commands. Ctrl-C stops safely."""
import argparse
import signal
import json
from pathlib import Path
import time
import numpy as np


class ScopeIO:
    def __init__(self, ip):
        self.ip = ip
        if ip.read(0x3c) != 0x45434733:
            raise RuntimeError('Wrong scope register ABI; double-buffer bitstream required')

    def command(self, data):
        if not 1 <= len(data) <= 16:
            raise ValueError('SPI transactions must have 1..16 bytes')
        if self.ip.read(0) & 4:
            raise RuntimeError('Disable automatic capture before register commands')
        end = time.monotonic() + 1
        while self.ip.read(4) & 1:
            if time.monotonic() > end:
                raise TimeoutError('SPI busy')
            time.sleep(0.0001)
        padded = bytes(data).ljust(16, b'\x00')
        for i in range(4):
            self.ip.write(0x100+i*4, int.from_bytes(padded[i*4:i*4+4], 'little'))
        self.ip.write(8, len(data))
        end = time.monotonic() + 1
        while not (self.ip.read(4) & 2):
            if time.monotonic() > end:
                raise TimeoutError('SPI command completion')
            time.sleep(0.0001)
        answer = b''.join(self.ip.read(0x200+i*4).to_bytes(4, 'little') for i in range(4))
        return answer[:len(data)]

    def initialize_adc(self, test_signal=False, rld_channel=1):
        # Preserve the legacy board's clock wiring. No external CLK is generated.
        self.ip.write(0, 0)
        time.sleep(0.1)
        self.ip.write(0, 1)
        time.sleep(0.1)
        self.command([0x11])  # SDATAC
        time.sleep(0.001)
        device_id = self.command([0x20, 0, 0])[2]
        if device_id not in (0x53, 0x73):
            raise RuntimeError(f'ADC ID 0x{device_id:02x}; check clock, power and isolated SPI wiring')
        config = [0x02, 0xa3 if test_signal else 0xa0, 0x10,
                  0x05 if test_signal else 0x00, 0x05 if test_signal else 0x00,
                  0x2c if test_signal else (0x23 if rld_channel == 1 else 0x2c), 0, 0, 0x02, 0x07, 0x0c]
        self.command([0x41, 10] + config)
        time.sleep(0.01)
        actual = list(self.command([0x21, 10]+[0]*11)[2:])
        for i, (got, want) in enumerate(zip(actual, config)):
            # LOFF_STAT includes read-only electrode status; GPIO input values vary.
            mask = 0x40 if i == 7 else (0x0c if i == 10 else 0xff)
            if (got & mask) != (want & mask):
                raise RuntimeError(f'ADC register {i+1:02x}: got {got:02x}, expected {want:02x}, mask {mask:02x}')
        time.sleep(1.0)
        self.ip.write(0, 9)  # clear FIFO, reset released, START low
        self.ip.write(0, 3)  # START high, automatic acquisition still off
        self.command([0x10]) # RDATAC
        self.ip.write(0, 7)  # enable DRDY-driven nine-byte reads
        return device_id, actual

    def select_rld_channel(self, channel):
        if channel not in (1, 2):
            raise ValueError('RLD channel must be 1 or 2')
        value = 0x23 if channel == 1 else 0x2c
        self.ip.write(0, 1)
        self.command([0x11])
        self.command([0x46, 0, value])
        actual = self.command([0x26, 0, 0])[2]
        if actual != value:
            raise RuntimeError('RLD configuration readback failed')
        self.ip.write(0, 9)
        self.ip.write(0, 3)
        self.command([0x10])
        self.ip.write(0, 7)
        print('RLD_CHANNEL', channel, 'REGISTER', hex(actual), flush=True)

    def drain(self, limit=64):
        status = self.ip.read(4)
        if status & 0x0c:
            raise RuntimeError(f'ADC frame loss or invalid status: overruns={self.ip.read(0x30)}, bad={self.ip.read(0x34)}')
        count = min((status >> 16) & 0x7ff, limit)
        data = np.empty((count, 2), dtype=np.int32)
        for i in range(count):
            frame_status = self.ip.read(0x20)
            if frame_status >> 20 != 0x0c:
                raise RuntimeError(f'Invalid ADC frame header {frame_status:06x}')
            ch1 = self.ip.read(0x24)
            ch2 = self.ip.read(0x28) # pop occurs only after this read is accepted
            data[i] = [ch1 if ch1 < 0x80000000 else ch1-0x100000000,
                       ch2 if ch2 < 0x80000000 else ch2-0x100000000]
        return data

    def draw(self, history):
        if self.ip.read(0x10) & 4:
            return False
        frame_state = self.ip.read(0x1c)
        if frame_state & 4:
            return False  # Previous submission is waiting for vertical blank.
        # Common automatic gain across all displayed channels/paths.
        peak = max(2048.0, float(np.percentile(np.abs(history.astype(np.float64)), 99.5)))
        y = np.clip(np.rint(260-history*150.0/peak), 81, 438).astype(np.uint32)
        edges = np.linspace(0, len(history), 641, dtype=int)[:-1]
        low = np.minimum.reduceat(y, edges, axis=0)
        high = np.maximum.reduceat(y, edges, axis=0)
        # Include the preceding sample at each column boundary, so steep QRS
        # edges remain connected between columns while preserving all extrema.
        previous = y[np.maximum(edges - 1, 0)]
        low = np.minimum(low, previous).transpose(1, 2, 0).reshape(-1)
        high = np.maximum(high, previous).transpose(1, 2, 0).reshape(-1)
        packed = (high << 10) | low
        # Write-only BRAM window: bank order CH1/diag, CH1/fast, CH2/diag, CH2/fast.
        self.ip.mmio.array[0x4000//4:0x6800//4] = packed
        self.ip.write(0x1c, 1 - (frame_state & 1))
        return True


def demo_samples(start, count):
    t = (np.arange(count)+start)/500.0
    phase = t % 0.82
    def pulse(center, width, amplitude):
        return amplitude*np.exp(-0.5*((phase-center)/width)**2)
    lead1 = pulse(.13,.025,2200)-pulse(.28,.009,3800)+pulse(.30,.009,21000)-pulse(.326,.015,6500)+pulse(.53,.065,6200)
    lead2 = .72*lead1+1900*np.sin(2*np.pi*1.4*t)+900*np.sin(2*np.pi*50*t)
    return np.rint(np.column_stack((lead1,lead2))).astype(np.int32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, default=Path(__file__).parent/'scope/ecg_scope.bit')
    parser.add_argument('--source', choices=['demo','adc-test','adc','replay'], default='demo')
    parser.add_argument('--input-channel', type=int, choices=[1,2], default=2, help='Startup channel: CN4=1, CN2=2; RLD follows BTN0/BTN1 in external ADC mode')
    parser.add_argument('--status', type=Path, help='Atomic live status JSON for service verification')
    parser.add_argument('--duration', type=float, default=0, help='Seconds; zero runs until Ctrl-C')
    parser.add_argument('--display-fps', type=float, default=25, help='Target waveform updates per second (1..60); HDMI scan remains 60 Hz')
    parser.add_argument('--summary', type=Path, default=Path(__file__).parent/'scope/run_summary.json')
    parser.add_argument('--recording', type=Path, help='Two-column int32 raw replay file')
    args = parser.parse_args()
    replay = np.load(args.recording,allow_pickle=False) if args.source=='replay' else None
    if replay is not None and (replay.ndim!=2 or replay.shape[1]!=2 or len(replay)<3000):
        parser.error('Replay needs at least 3000 samples and two columns')
    replay_pos=0
    if args.duration < 0:
        parser.error('duration cannot be negative')
    if not 1 <= args.display_fps <= 60:
        parser.error('display-fps must be between 1 and 60')
    import fcntl
    # One process must own the FPGA, including notebook and service launches.
    lock_handle = open('/run/lock/ecg-scope.lock', 'a')
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('ECG scope is already running; stop ecg-scope.service first')
    def stop_signal(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_signal)
    from pynq import Overlay, allocate
    overlay = Overlay(str(args.overlay))
    io = ScopeIO(overlay.ecg_io)
    filt = overlay.ecg_filter_0
    ib = allocate(shape=(4096,8),dtype=np.int32)
    ob = allocate(shape=(4096,8,2),dtype=np.int32)
    history = np.zeros((2000,2,2),dtype=np.int32)
    seen = 0
    warmup_remaining = 543
    warmup_discarded = 0
    filter_reset = True
    rld_channel = args.input_channel
    rld_switches = 0
    last_status = time.monotonic()
    filtering_active = False
    started = time.monotonic()
    next_demo = started
    next_draw = started
    draw_period = 1.0 / args.display_fps
    draw_count = 0
    draw_first = None
    draw_last = None
    draw_total_seconds = 0.0
    draw_max_seconds = 0.0
    last_data = started
    device_id = None
    error = None
    try:
        io.ip.write(0x14,args.input_channel-1)  # selected channel, diagnostic, live
        io.ip.write(0x18,1 if args.source in ['demo','replay'] else 2)
        if args.source in ['adc','adc-test']:
            device_id, registers = io.initialize_adc(args.source=='adc-test', rld_channel)
            print('ADC ID',hex(device_id),'registers',[hex(x) for x in registers],flush=True)
            last_data=time.monotonic()
        print('SOURCE',args.source,'HDMI_HPD',io.ip.read(0x38),'BUTTONS: BTN0 CH1 / BTN1 CH2 / BTN2 PATH / BTN3 HOLD',flush=True)
        while args.duration==0 or time.monotonic()-started < args.duration:
            now = time.monotonic()
            if args.source == 'adc':
                selected_channel = (io.ip.read(0x10) & 1) + 1
                if selected_channel != rld_channel:
                    io.select_rld_channel(selected_channel)
                    rld_channel = selected_channel
                    rld_switches += 1
                    warmup_remaining = 543
                    filter_reset = True
                    history.fill(0)
                    io.ip.write(0x18, 2)
                    last_data = time.monotonic()
            if args.source=='replay':
                if now < next_demo:
                    time.sleep(min(.002,next_demo-now));continue
                if replay_pos>=len(replay):
                    replay_pos=0;warmup_remaining=543;filter_reset=True;history.fill(0)
                    io.feed_replay(None,True)
                raw=replay[replay_pos:replay_pos+5].copy();replay_pos+=len(raw)
                io.feed_replay(raw,False)
                next_demo=max(next_demo+len(raw)/500,now+.001)
            elif args.source=='demo':
                if now < next_demo:
                    time.sleep(min(.002,next_demo-now));continue
                raw = demo_samples(seen,10)
                next_demo = max(next_demo+.02,now+.001)
            else:
                raw = io.drain()
                if not len(raw):
                    if now-last_data>1:
                        raise TimeoutError('No DRDY frames for one second; check CLKSEL/clock and isolated wiring')
                    time.sleep(.001);continue
                last_data=now
            n=len(raw)
            ib[:n]=0;ib[:n,:2]=raw;ob[:n]=0
            ib.flush();ob.flush()
            for offset,address in [(0x10,int(ib.physical_address)),(0x1c,int(ob.physical_address))]:
                filt.write(offset,address&0xffffffff);filt.write(offset+4,address>>32)
            filt.write(0x28,n);filt.write(0x30,int(filter_reset))
            filter_reset = False
            filtering_active=True;filt.write(0,1)
            deadline=time.monotonic()+1
            while not filt.read(0)&2:
                if time.monotonic()>deadline:raise TimeoutError('HLS filter did not finish')
                time.sleep(.0001)
            filtering_active=False;ob.invalidate()
            # Discard warmup once per reset, preserving all later cross-block state.
            skip=min(n,warmup_remaining)
            warmup_remaining-=skip
            warmup_discarded+=skip
            valid=ob[skip:n,:2,:].copy()
            seen+=n
            if len(valid):
                history=np.roll(history,-len(valid),axis=0);history[-len(valid):]=valid
                io.ip.write(0x18,1 if args.source in ['demo','replay'] else (3 if args.source=='adc-test' else 0))
            draw_started = time.monotonic()
            if warmup_remaining == 0 and draw_started >= next_draw:
                drawn = io.draw(history)
                draw_finished = time.monotonic()
                next_draw = max(next_draw + draw_period, draw_finished)
                if drawn:
                    draw_count += 1
                    if draw_first is None:
                        draw_first = draw_started
                    draw_last = draw_started
                    draw_seconds = draw_finished - draw_started
                    draw_total_seconds += draw_seconds
                    draw_max_seconds = max(draw_max_seconds, draw_seconds)
            if args.status and now-last_status >= 1:
                status = dict(source=args.source, pid=__import__('os').getpid(),
                              boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                              uptime_seconds=time.monotonic()-started,
                              samples_per_channel=seen, warmup_remaining=warmup_remaining,
                              rld_channel=rld_channel, rld_switches=rld_switches,
                              ui_state=io.ip.read(0x10)&7,
                              display_updates=draw_count,
                              display_measured_fps=(draw_count-1)/(draw_last-draw_first) if draw_count>1 else None,
                              overruns=io.ip.read(0x30),bad_frames=io.ip.read(0x34))
                args.status.parent.mkdir(parents=True,exist_ok=True)
                temp=args.status.with_suffix('.tmp')
                temp.write_text(json.dumps(status,indent=2)+'\n')
                temp.replace(args.status)
                last_status=now
    except KeyboardInterrupt:
        print('Stopped by user',flush=True)
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
        io.ip.write(0x18,2)
        raise
    finally:
        io.ip.write(0,1) # no further DRDY reads or conversions
        selected=io.ip.read(0x10)&3
        io.ip.write(0x14,selected|4) # freeze final display
        summary={'source':args.source,'samples_per_channel':seen,'warmup_discarded':warmup_discarded,'rld_channel':rld_channel,'rld_switches':rld_switches,
                 'device_id':device_id,'hdmi_hpd':io.ip.read(0x38),
                 'ui_state':io.ip.read(0x10)&7,'overruns':io.ip.read(0x30),'bad_frames':io.ip.read(0x34),
                 'elapsed_seconds':time.monotonic()-started,'error':error,
                 'display_target_fps':args.display_fps,'display_updates':draw_count,
                 'display_measured_fps':(draw_count-1)/(draw_last-draw_first) if draw_count>1 else None,
                 'draw_mean_ms':1000*draw_total_seconds/draw_count if draw_count else None,
                 'draw_max_ms':1000*draw_max_seconds,
                 'note':'HPD does not prove a visible image. Demo samples are synthetic; physical HDMI/ADC validation requires connected hardware.'}
        args.summary.parent.mkdir(parents=True,exist_ok=True)
        args.summary.write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary,indent=2),flush=True)
        if not filtering_active:
            ib.freebuffer();ob.freebuffer()
        lock_handle.close()


if __name__=='__main__':
    main()

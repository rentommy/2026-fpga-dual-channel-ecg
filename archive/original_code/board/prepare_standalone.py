"""Create the standalone runner from the verified Chinese scope runner."""
from pathlib import Path

root = Path(__file__).resolve().parent
s = (root / 'run_scope.py').read_text(encoding='utf-8')

def replace(old, new):
    global s
    assert s.count(old) == 1, old
    s = s.replace(old, new)

replace('import argparse\n', 'import argparse\nimport signal\n')
replace('    def initialize_adc(self, test_signal=False):',
        '    def initialize_adc(self, test_signal=False, rld_channel=1):')
replace('                  0x2c, 0, 0, 0x02, 0x07, 0x0c]',
        '                  0x2c if test_signal else (0x23 if rld_channel == 1 else 0x2c), 0, 0, 0x02, 0x07, 0x0c]')
replace('    def drain(self, limit=64):', '''    def select_rld_channel(self, channel):
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

    def drain(self, limit=64):''')
replace("    parser.add_argument('--duration',", "    parser.add_argument('--input-channel', type=int, choices=[1,2], default=2, help='Startup channel: CN4=1, CN2=2; RLD follows BTN0/BTN1 in external ADC mode')\n    parser.add_argument('--status', type=Path, help='Atomic live status JSON for service verification')\n    parser.add_argument('--duration',")
replace('    from pynq import Overlay, allocate', '''    import fcntl
    # One process must own the FPGA, including notebook and service launches.
    lock_handle = open('/run/lock/ecg-scope.lock', 'a')
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('ECG scope is already running; stop ecg-scope.service first')
    def stop_signal(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_signal)
    from pynq import Overlay, allocate''')
replace('    seen = 0', '    seen = 0\n    warmup_remaining = 543\n    warmup_discarded = 0\n    filter_reset = True\n    rld_channel = args.input_channel\n    rld_switches = 0\n    last_status = time.monotonic()')
replace('        io.ip.write(0x14,0)  # CH1, diagnostic, live',
        '        io.ip.write(0x14,args.input_channel-1)  # selected channel, diagnostic, live')
replace("            device_id, registers = io.initialize_adc(args.source=='adc-test')",
        "            device_id, registers = io.initialize_adc(args.source=='adc-test', rld_channel)")
replace('            now = time.monotonic()', '''            now = time.monotonic()
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
                    last_data = time.monotonic()''')
replace('            filt.write(0x28,n);filt.write(0x30,int(seen==0))',
        '            filt.write(0x28,n);filt.write(0x30,int(filter_reset))\n            filter_reset = False')
replace('            skip=max(0,min(n,543-seen))',
        '            skip=min(n,warmup_remaining)\n            warmup_remaining-=skip\n            warmup_discarded+=skip')
replace('            if seen > 543 and draw_started >= next_draw:',
        '            if warmup_remaining == 0 and draw_started >= next_draw:')
replace('    except KeyboardInterrupt:', '''            if args.status and now-last_status >= 1:
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
                temp.write_text(json.dumps(status,indent=2)+'\\n')
                temp.replace(args.status)
                last_status=now
    except KeyboardInterrupt:''')
replace("'warmup_discarded':min(seen,543)", "'warmup_discarded':warmup_discarded,'rld_channel':rld_channel,'rld_switches':rld_switches")
replace('            ib.freebuffer();ob.freebuffer()',
        '            ib.freebuffer();ob.freebuffer()\n        lock_handle.close()')
compile(s, 'run_scope_standalone.py', 'exec')
(root/'run_scope_standalone.py').write_text(s,encoding='utf-8')
print('STANDALONE_RUNNER_PREPARED')

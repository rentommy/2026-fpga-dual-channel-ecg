"""Staged PYNQ diagnostics. Run one stage at a time after reviewing its log."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["parse", "load", "control", "sample"], default="parse")
    parser.add_argument("--overlay", type=Path, default=root / "board/overlay/ecg_filter.bit")
    args = parser.parse_args()
    log_path = root / "board/overlay/probe_trace.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def trace(event, **details):
        line = json.dumps({"time": time.time(), "stage": args.stage, "event": event, **details})
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(line, flush=True)

    trace("import_begin")
    import numpy as np
    import pynq
    from pynq import Overlay, allocate
    trace("import_end", pynq=pynq.__version__, board=os.environ.get("BOARD"))
    trace("parse_begin")
    overlay = Overlay(str(args.overlay), download=False)
    trace("parse_end", ips=list(overlay.ip_dict), clocks=overlay.clock_dict)
    if args.stage == "parse":
        return
    trace("download_begin")
    overlay.download()
    trace("download_end", loaded=overlay.is_loaded())
    if args.stage == "load":
        return
    trace("driver_begin")
    ip = overlay.ecg_filter_0
    trace("driver_end")
    trace("control_read_begin")
    control = ip.read(0)
    trace("control_read_end", control=hex(control))
    if args.stage == "control":
        return
    trace("allocate_begin")
    inputs = allocate(shape=(1, 8), dtype=np.int32)
    outputs = None
    completed = False
    try:
        outputs = allocate(shape=(1, 8, 2), dtype=np.int32)
        trace("allocate_end", input_address=int(inputs.physical_address),
              output_address=int(outputs.physical_address))
        inputs[:] = 0
        outputs[:] = 0
        inputs.flush()
        outputs.flush()
        for offset, address in [(0x10, int(inputs.physical_address)),
                                (0x1C, int(outputs.physical_address))]:
            trace("address_write_begin", offset=hex(offset))
            ip.write(offset, address & 0xFFFFFFFF)
            ip.write(offset + 4, address >> 32)
            trace("address_write_end", offset=hex(offset))
        ip.write(0x28, 1)
        ip.write(0x30, 1)
        trace("start_write_begin")
        ip.write(0, 1)
        trace("start_write_end")
        before = time.monotonic()
        while not (ip.read(0) & 2):
            if time.monotonic() - before > 5:
                raise TimeoutError("Single-sample completion timed out")
            time.sleep(0.001)
        completed = True
        outputs.invalidate()
        trace("sample_done", values=outputs.tolist())
        assert np.all(outputs == 0), "Zero input after reset must produce zero output"
    finally:
        # Never free a DDR buffer that an unfinished AXI master may still use.
        if completed:
            inputs.freebuffer()
            if outputs is not None:
                outputs.freebuffer()
        else:
            trace("buffers_not_explicitly_freed_reboot_required")


if __name__ == "__main__":
    main()

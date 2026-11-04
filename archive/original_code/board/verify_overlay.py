"""Replay saved samples on PYNQ; this is not a live ECG acquisition program."""
import argparse
import json
from pathlib import Path
import time


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", type=Path, default=root / "board/overlay/ecg_filter.bit")
    parser.add_argument("--input", type=Path, default=root / "data/input_raw.txt")
    parser.add_argument("--golden", type=Path, default=root / "data/golden_float.txt")
    parser.add_argument("--block-size", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=root / "board/overlay/board_output.npy")
    args = parser.parse_args()
    if not 1 <= args.block_size <= 4096 or args.timeout <= 0:
        parser.error("block-size must be 1..4096 and timeout must be positive")

    import numpy as np
    from pynq import Overlay, allocate

    raw = np.atleast_1d(np.loadtxt(args.input, dtype=np.int64))
    golden = np.atleast_1d(np.loadtxt(args.golden, dtype=np.float64))
    if raw.ndim != 1 or golden.ndim != 1 or len(raw) != len(golden) or len(raw) <= 543:
        raise ValueError("Input/reference must be equal-length one-column records longer than 543 samples")
    if np.any(raw < -(1 << 23)) or np.any(raw >= (1 << 23)) or not np.all(np.isfinite(golden)):
        raise ValueError("Invalid 24-bit samples or non-finite reference")
    if not args.overlay.is_file() or not args.overlay.with_suffix(".hwh").is_file():
        raise FileNotFoundError("Matching .bit and .hwh files are required")

    overlay = Overlay(str(args.overlay))
    ip = overlay.ecg_filter_0
    inputs = allocate(shape=(args.block_size, 8), dtype=np.int32)
    outputs = None
    try:
        outputs = allocate(shape=(args.block_size, 8, 2), dtype=np.int32)
        result = np.empty((len(raw), 8, 2), dtype=np.int32)
        timings = []
        for start in range(0, len(raw), args.block_size):
            count = min(args.block_size, len(raw) - start)
            inputs[:count, :] = raw[start:start + count, None]
            outputs[:] = 0
            inputs.flush()
            outputs.flush()
            for offset, address in [(0x10, int(inputs.physical_address)),
                                    (0x1C, int(outputs.physical_address))]:
                ip.write(offset, address & 0xFFFFFFFF)
                ip.write(offset + 4, address >> 32)
            ip.write(0x28, count)
            ip.write(0x30, int(start == 0))
            before = time.monotonic()
            ip.write(0x00, 1)
            while not (ip.read(0x00) & 2):
                if time.monotonic() - before > args.timeout:
                    raise TimeoutError(f"Filter did not complete block starting at {start}")
                time.sleep(0.0001)
            timings.append(time.monotonic() - before)
            outputs.invalidate()
            result[start:start + count] = outputs[:count]
    finally:
        inputs.freebuffer()
        if outputs is not None:
            outputs.freebuffer()

    # ch2/ch3 path0 are intentionally configured for the fast path, so exclude
    # them from the diagnostic-reference comparison. This input is duplicated
    # across channels; it does not establish isolation for arbitrary inputs.
    errors = result[543:, [0, 1, 4, 5, 6, 7], 0].astype(np.float64) - golden[543:, None]
    maximum = float(np.max(np.abs(errors)))
    rms = float(np.sqrt(np.mean(errors ** 2)))
    passed = maximum <= 64.0 and rms <= 8.0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, result)
    summary = {"passed": passed, "samples_per_channel": len(raw), "channels": 8,
               "paths": 2, "warmup_discarded": 543, "block_size": args.block_size,
               "max_error_codes": maximum, "rms_error_codes": rms,
               "max_block_wall_seconds": max(timings),
               "note": "Wall time includes polling/host overhead; this is file replay, not end-to-end live latency."}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

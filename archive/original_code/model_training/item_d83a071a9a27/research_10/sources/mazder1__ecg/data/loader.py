"""
Data loading utilities.
Supports WFDB (PhysioNet) records and Hugging Face datasets.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import wfdb
from datasets import load_dataset

from config.config import cfg


# ── WFDB ──────────────────────────────────────────────────────────────────────

def load_wfdb_record(
    record_name: str,
    data_dir: Optional[Path] = None,
    channel_names: Optional[list] = None,
) -> tuple[np.ndarray, dict]:
    """
    Load a single WFDB record.

    Args:
        record_name: Record name, e.g. "100" for mitdb/100.
        data_dir:    Directory containing .dat/.hea files.
                     Defaults to cfg.paths.data_dir.
        channel_names: List of channel names to select.
                       None = load all channels.

    Returns:
        signal:  np.ndarray of shape (n_samples, n_channels)
        info:    dict with fs, units, sig_name, comments, …
    """
    data_dir = data_dir or cfg.paths.data_dir
    record_path = str(data_dir / record_name)

    record = wfdb.rdrecord(record_path)
    signal = record.p_signal   # (n_samples, n_channels), float64

    if channel_names is not None:
        idx = [record.sig_name.index(ch) for ch in channel_names]
        signal = signal[:, idx]

    info = {
        "fs":       record.fs,
        "n_sig":    record.n_sig,
        "sig_name": record.sig_name,
        "units":    record.units,
        "comments": record.comments,
    }
    return signal.astype(np.float32), info


def load_wfdb_annotation(
    record_name: str,
    data_dir: Optional[Path] = None,
    annotator: str = "atr",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Load beat annotations for a WFDB record.

    Returns:
        samples: sample indices of each annotation
        symbols: annotation symbol for each sample (e.g. 'N', 'V', …)
    """
    data_dir = data_dir or cfg.paths.data_dir
    record_path = str(data_dir / record_name)

    ann = wfdb.rdann(record_path, annotator)
    return np.array(ann.sample), np.array(ann.symbol)


def load_wfdb_database(
    record_list: list[str],
    data_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Load multiple WFDB records.

    Returns:
        List of dicts with keys: name, signal, fs, annotations
    """
    data_dir = data_dir or cfg.paths.data_dir
    records = []
    for name in record_list:
        signal, info = load_wfdb_record(name, data_dir)
        samples, symbols = load_wfdb_annotation(name, data_dir)
        records.append({
            "name":     name,
            "signal":   signal,
            "info":     info,
            "ann_samples":  samples,
            "ann_symbols":  symbols,
        })
    return records


def download_wfdb_database(db_name: str, dest: Optional[Path] = None):
    """
    Download a PhysioNet database via WFDB.

    Args:
        db_name: e.g. "mitdb", "ptbdb", "ludb"
        dest:    destination directory (default cfg.paths.data_dir)
    """
    dest = dest or cfg.paths.data_dir
    dest.mkdir(parents=True, exist_ok=True)
    wfdb.dl_database(db_name, str(dest))
    print(f"Downloaded '{db_name}' to {dest}")


# ── MIT-BIH ───────────────────────────────────────────────────────────────────

# AAMI beat class mapping (5-class standard)
_MITBIH_LABEL_MAP = {
    # N — Normal / bundle branch block / escape
    "N": 0, "L": 0, "R": 0, "e": 0, "j": 0,
    # S — Supraventricular ectopic
    "A": 1, "a": 1, "J": 1, "S": 1,
    # V — Ventricular ectopic
    "V": 2, "E": 2,
    # F — Fusion
    "F": 3,
    # Q — Unknown / paced
    "/": 4, "f": 4, "Q": 4,
}

_MITBIH_RECORDS = [
    "100", "101", "102", "103", "104", "105", "106", "107", "108", "109",
    "111", "112", "113", "114", "115", "116", "117", "118", "119",
    "121", "122", "123", "124",
    "200", "201", "202", "203", "205", "207", "208", "209", "210",
    "212", "213", "214", "215", "217", "219", "220", "221", "222", "223",
    "228", "230", "231", "232", "233", "234",
]


def load_mitbih_dataset(
    data_dir: Optional[Path] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Load, preprocess, and extract beat windows from the MIT-BIH Arrhythmia DB.

    Each sample is a fixed-length window centered slightly left of an R-peak,
    labelled with the AAMI 5-class scheme (N / S / V / F / Q).

    Args:
        data_dir: directory containing the MIT-BIH .dat/.hea/.atr files.
                  Defaults to cfg.paths.data_dir.  The database is
                  downloaded automatically if the directory is empty.

    Returns:
        signals: np.ndarray  (n_beats, segment_len, n_leads)  float32
        labels:  np.ndarray  (n_beats,)                       int64
    """
    from data.preprocessing import preprocess_record

    data_dir = data_dir or cfg.paths.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    # Auto-download if no .dat files are present
    if not any(data_dir.glob("*.dat")):
        print(f"MIT-BIH data not found in {data_dir} — downloading …")
        download_wfdb_database("mitdb", data_dir)

    # Window: 100 samples before R-peak, remainder after
    before = 100
    after  = cfg.data.segment_len - before

    all_signals: list[np.ndarray] = []
    all_labels:  list[int]        = []

    for name in _MITBIH_RECORDS:
        try:
            signal, info = load_wfdb_record(name, data_dir)
            r_samples, symbols = load_wfdb_annotation(name, data_dir)
        except Exception as exc:
            print(f"  Skipping record {name}: {exc}")
            continue

        # Select configured leads only
        signal = signal[:, :cfg.data.n_leads]

        # Preprocess (resample only if fs differs from target)
        signal = preprocess_record(
            signal,
            fs=info["fs"],
            target_fs=cfg.data.fs,
            lowcut=cfg.data.lowcut,
            highcut=cfg.data.highcut,
            filter_order=cfg.data.filter_order,
        )

        # Rescale annotation indices if resampling changed the rate
        if info["fs"] != cfg.data.fs:
            r_samples = (r_samples * cfg.data.fs / info["fs"]).astype(int)

        n = signal.shape[0]
        for r, sym in zip(r_samples, symbols):
            label = _MITBIH_LABEL_MAP.get(sym)
            if label is None:
                continue          # skip rhythm / non-beat annotations
            lo, hi = r - before, r + after
            if lo < 0 or hi > n:
                continue          # skip beats too close to record edges
            all_signals.append(signal[lo:hi])   # (segment_len, n_leads)
            all_labels.append(label)

    if not all_signals:
        raise RuntimeError("No beat windows were extracted. Check data_dir and annotations.")

    print(f"  Extracted {len(all_signals)} beat windows from MIT-BIH.")
    return np.stack(all_signals), np.array(all_labels, dtype=np.int64)


# ── Hugging Face datasets ─────────────────────────────────────────────────────

def load_hf_dataset(
    name: str = None,
    split: str = "train",
    **kwargs,
):
    """
    Load a dataset from the Hugging Face Hub.

    Args:
        name:  Dataset identifier, e.g. "sileod/ecg-arrhythmia".
               Defaults to cfg.data.hf_dataset.
        split: "train", "test", "validation"
        **kwargs: Passed through to datasets.load_dataset().

    Returns:
        datasets.Dataset object
    """
    name = name or cfg.data.hf_dataset
    ds = load_dataset(name, split=split, **kwargs)
    return ds

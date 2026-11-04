"""
Signal preprocessing utilities.
Filtering, normalization, and segmentation of ECG signals.
"""

import numpy as np
from scipy.signal import butter, filtfilt, resample_poly
from typing import Optional


# ── Filtering ─────────────────────────────────────────────────────────────────

def butter_bandpass(
    lowcut: float,
    highcut: float,
    fs: float,
    order: int = 4,
) -> tuple:
    """Design a Butterworth bandpass filter. Returns (b, a) coefficients."""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype="band")
    return b, a


def butter_bandpass_filter(
    signal: np.ndarray,
    lowcut: float,
    highcut: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """
    Apply a zero-phase Butterworth bandpass filter (filtfilt).

    Args:
        signal:  (n_samples,) or (n_samples, n_leads)
        lowcut:  low cut-off frequency in Hz
        highcut: high cut-off frequency in Hz
        fs:      sampling frequency in Hz
        order:   filter order

    Returns:
        Filtered signal, same shape as input.
    """
    b, a = butter_bandpass(lowcut, highcut, fs, order)
    if signal.ndim == 1:
        return filtfilt(b, a, signal).astype(np.float32)
    # Apply per-lead
    return np.stack(
        [filtfilt(b, a, signal[:, i]) for i in range(signal.shape[1])],
        axis=1,
    ).astype(np.float32)


def butter_lowpass_filter(
    signal: np.ndarray,
    cutoff: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """Zero-phase Butterworth low-pass filter."""
    nyq = 0.5 * fs
    b, a = butter(order, cutoff / nyq, btype="low")
    if signal.ndim == 1:
        return filtfilt(b, a, signal).astype(np.float32)
    return np.stack(
        [filtfilt(b, a, signal[:, i]) for i in range(signal.shape[1])],
        axis=1,
    ).astype(np.float32)


def butter_highpass_filter(
    signal: np.ndarray,
    cutoff: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """Zero-phase Butterworth high-pass filter (baseline wander removal)."""
    nyq = 0.5 * fs
    b, a = butter(order, cutoff / nyq, btype="high")
    if signal.ndim == 1:
        return filtfilt(b, a, signal).astype(np.float32)
    return np.stack(
        [filtfilt(b, a, signal[:, i]) for i in range(signal.shape[1])],
        axis=1,
    ).astype(np.float32)


# ── Resampling ────────────────────────────────────────────────────────────────

def resample_signal(
    signal: np.ndarray,
    orig_fs: int,
    target_fs: int,
) -> np.ndarray:
    """Resample signal from orig_fs to target_fs using polyphase filtering."""
    from math import gcd
    g = gcd(orig_fs, target_fs)
    up, down = target_fs // g, orig_fs // g
    if signal.ndim == 1:
        return resample_poly(signal, up, down).astype(np.float32)
    return np.stack(
        [resample_poly(signal[:, i], up, down) for i in range(signal.shape[1])],
        axis=1,
    ).astype(np.float32)


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize_signal(
    signal: np.ndarray,
    method: str = "zscore",
) -> np.ndarray:
    """
    Normalize an ECG signal.

    Args:
        signal: (n_samples,) or (n_samples, n_leads)
        method: "zscore" | "minmax" | "robust"

    Returns:
        Normalized signal, same shape.
    """
    signal = signal.astype(np.float32)
    if method == "zscore":
        mu  = signal.mean(axis=0, keepdims=True)
        std = signal.std(axis=0, keepdims=True) + 1e-8
        return (signal - mu) / std
    elif method == "minmax":
        mn = signal.min(axis=0, keepdims=True)
        mx = signal.max(axis=0, keepdims=True)
        return (signal - mn) / (mx - mn + 1e-8)
    elif method == "robust":
        median = np.median(signal, axis=0, keepdims=True)
        iqr    = (np.percentile(signal, 75, axis=0) -
                  np.percentile(signal, 25, axis=0) + 1e-8)
        return (signal - median) / iqr
    else:
        raise ValueError(f"Unknown normalization method: {method!r}")


# ── Segmentation ──────────────────────────────────────────────────────────────

def segment_signal(
    signal: np.ndarray,
    segment_len: int,
    stride: int,
) -> np.ndarray:
    """
    Slice a signal into fixed-length overlapping windows.

    Args:
        signal:      (n_samples,) or (n_samples, n_leads)
        segment_len: window length in samples
        stride:      step size in samples

    Returns:
        segments: (n_segments, segment_len) or (n_segments, segment_len, n_leads)
    """
    n = signal.shape[0]
    starts = range(0, n - segment_len + 1, stride)
    if signal.ndim == 1:
        return np.stack([signal[s: s + segment_len] for s in starts])
    return np.stack([signal[s: s + segment_len, :] for s in starts])


def extract_beat_windows(
    signal: np.ndarray,
    r_peaks: np.ndarray,
    before: int,
    after: int,
) -> np.ndarray:
    """
    Extract fixed-size windows centered on annotated R-peaks.

    Args:
        signal:  (n_samples,) raw ECG
        r_peaks: sample indices of R-peaks
        before:  samples to include before each R-peak
        after:   samples to include after each R-peak

    Returns:
        beats: (n_beats, before+after) float32
    """
    n = signal.shape[0]
    beats = []
    for r in r_peaks:
        lo, hi = r - before, r + after
        if lo >= 0 and hi <= n:
            beats.append(signal[lo:hi])
    return np.stack(beats).astype(np.float32) if beats else np.empty((0, before + after))


# ── Full preprocessing pipeline ───────────────────────────────────────────────

def preprocess_record(
    signal: np.ndarray,
    fs: int,
    target_fs: int = 360,
    lowcut: float = 0.5,
    highcut: float = 40.0,
    filter_order: int = 4,
    normalize: str = "zscore",
) -> np.ndarray:
    """
    Full preprocessing pipeline:
      1. Resample (if needed)
      2. Bandpass filter
      3. Normalize

    Args:
        signal:     raw ECG (n_samples,) or (n_samples, n_leads)
        fs:         original sampling frequency
        target_fs:  desired sampling frequency
        lowcut:     bandpass low cut-off (Hz)
        highcut:    bandpass high cut-off (Hz)
        filter_order: Butterworth filter order
        normalize:  normalization method

    Returns:
        Preprocessed signal, float32.
    """
    if fs != target_fs:
        signal = resample_signal(signal, fs, target_fs)
    signal = butter_bandpass_filter(signal, lowcut, highcut, target_fs, filter_order)
    signal = normalize_signal(signal, method=normalize)
    return signal

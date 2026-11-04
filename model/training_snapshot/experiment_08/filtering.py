"""User-requested forward/backward bandpass followed by 50 Hz notch."""
import numpy as np
from scipy import signal

def filter_ecg(x, fs):
    x = np.asarray(x, dtype=np.float64)
    if fs <= 100:
        raise ValueError('50 Hz notch requires sampling rate above 100 Hz')
    sos = signal.butter(3, [0.5, 40.0], btype='bandpass', fs=fs, output='sos')
    y = signal.sosfiltfilt(sos, x)
    b, a = signal.iirnotch(50.0, 30.0, fs=fs)
    return signal.sosfiltfilt(signal.tf2sos(b, a), y)

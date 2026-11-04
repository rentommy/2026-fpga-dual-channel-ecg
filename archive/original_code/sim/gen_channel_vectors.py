"""Deterministic, bounded, distinct stimuli; no real personal ECG recording."""
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parent.parent
dest = root / "board/channel_test"
dest.mkdir(exist_ok=True)
n = np.arange(4096)
rng = np.random.default_rng(1292)
x = np.zeros((len(n), 8), dtype=np.int32)
x[31, 0] = 120000
x[679, 0] = -90000
x[:, 1] = np.rint(70000*np.sin(2*np.pi*5*n/500))
x[:, 2] = np.rint(60000*np.sin(2*np.pi*17*n/500))
x[:, 3] = np.where((n >= 400) & (n < 1900), 80000, -20000)
x[:, 4] = np.rint(55000*np.sin(2*np.pi*50*n/500))
x[:, 5] = rng.integers(-65000, 65001, len(n))
x[:, 6] = np.where(n%137 < 20, 50000, -35000)
# ch7 is a zero sentinel in the mixed case; excite it in its own isolation case.
x.astype('<i4').tofile(dest/'distinct_input.bin')
print('Generated', x.shape, 'peak', int(np.max(np.abs(x))))

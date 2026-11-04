# Public test data

This directory contains generated synthetic test inputs and corresponding references. It does not contain the team's personal ECG recordings. Run python sim/make_synthetic_data.py then python sim/gen_vectors.py to regenerate filter fixtures. They are test signals, not clinical data.

The 49-beat real-record deployment results in report/evidence are numerical comparison evidence. Their source recordings are local-only, so that exact experiment cannot be reproduced from this public candidate. Synthetic model inputs allow independent CPU/FPGA numerical checks without distributing personal recordings.

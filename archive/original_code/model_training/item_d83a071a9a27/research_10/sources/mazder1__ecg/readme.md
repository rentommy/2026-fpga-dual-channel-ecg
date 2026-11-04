# ECG CNN-Transformer — Arrhythmia Classification

A CNN + Transformer model trained on the MIT-BIH Arrhythmia Database for 5-class ECG beat classification.

## Model

**Architecture:** 1D CNN backbone (local feature extraction) → Transformer encoder → classification head

| Component | Details |
|---|---|
| CNN | 2-layer Conv1d, 8× downsampling |
| Transformer | 4 layers, d_model=128, 8 heads |
| Input | 1024-sample ECG segments, 1 lead (MLII), 360 Hz |
| Output | 5 classes (AAMI standard) |

**Classes:**

| Label | Meaning |
|---|---|
| N | Normal beat |
| S | Supraventricular ectopic |
| V | Ventricular ectopic |
| F | Fusion beat |
| Q | Unknown / paced |

## Checkpoints

All checkpoints are included in `checkpoints/`. Training ran for 50 epochs, saved every 5.

```
checkpoints/
├── best.pt        ← best validation loss
├── final.pt       ← epoch 50
├── epoch005.pt
├── epoch010.pt
├── ...
└── epoch050.pt
```

## Test set results (final checkpoint — epoch 50)

Evaluated on the held-out test split of MIT-BIH (16 398 beat windows, same seed as training).

| Metric | Score |
|---|---|
| Accuracy | **99.26%** |
| F1 (macro) | **95.38%** |

Per-class breakdown:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| N — Normal | 1.00 | 1.00 | 1.00 | 13 616 |
| S — Supraventricular | 0.93 | 0.93 | 0.93 | 391 |
| V — Ventricular | 0.98 | 0.98 | 0.98 | 1 076 |
| F — Fusion | 0.88 | 0.86 | 0.87 | 120 |
| Q — Unknown/Paced | 1.00 | 1.00 | 1.00 | 1 195 |

## Quick start

```bash
git clone https://github.com/mazder1/ECG.git
cd ECG
pip install -r requirements.txt

# Download MIT-BIH data (first run only, ~100 MB)
python -c "from data.loader import download_wfdb_database; download_wfdb_database('mitdb')"

# Evaluate the highest f1-score checkpoint
python scripts/evaluate.py --checkpoint checkpoints/epoch050.pt

# Evaluate the lowest validation loss checkpoint
python scripts/evaluate.py --checkpoint checkpoints/best.pt

# Or check a specific epoch
python scripts/evaluate.py --checkpoint checkpoints/epoch030.pt
```

The script prints accuracy, F1, AUC and saves a confusion matrix to `figures/`.

## Quick score check (no inference needed)

To see training/validation metrics for every checkpoint without running the model:

```python
import torch, glob

for f in sorted(glob.glob("checkpoints/*.pt")):
    ck = torch.load(f, map_location="cpu", weights_only=False)
    h  = ck["history"]
    print(f"{f:35s}  epoch={ck['epoch']:3d}  val_loss={h['val_loss'][-1]:.4f}  val_acc={h['val_acc'][-1]:.4f}")
```

## Structure

```
ECG/
├── checkpoints/         ← all saved .pt files
├── config/config.py     ← hyperparameters and paths
├── data/                ← MIT-BIH loading and preprocessing
├── models/
│   ├── ecg_cnntransformers.py  ← CNN + Transformer architecture
│   └── heads.py                ← classification head
├── training/metrics.py  ← accuracy, F1, AUC, confusion matrix
├── scripts/evaluate.py  ← evaluation entry point
├── utils/               ← helpers and visualization
└── figures/             ← confusion matrix and training curves
```

## License

MIT — see [LICENSE](LICENSE).

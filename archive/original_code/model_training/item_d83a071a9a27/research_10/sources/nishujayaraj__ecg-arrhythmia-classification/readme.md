# ECG Arrhythmia Classification
**MIT-BIH Dataset | ANN vs 1D-CNN vs LSTM | DWT Denoising | SMOTE | MLflow**

A deep learning project that classifies 14 types of cardiac arrhythmias from raw ECG signals using the MIT-BIH Arrhythmia Database. Three architectures (ANN, 1D-CNN, LSTM) were trained, compared, and tracked using MLflow experiment tracking.

---

## Results

| Model | Accuracy | F1 (Macro) | F1 (Weighted) | Epochs | Training Time |
|-------|----------|------------|---------------|--------|---------------|
| **LSTM** | **99.73%** | **99.70%** | **99.73%** | 20 | ~1.4h |
| ANN | 99.64% | 99.60% | 99.64% | 50 | ~23min |
| 1D-CNN | 99.52% | 99.45% | 99.52% | ~15 (early stop) | ~18min |

**Key finding:** LSTM outperformed both ANN and CNN despite training for only 20 epochs. ANN surprisingly beat CNN — likely because SMOTE's linear interpolation creates smooth synthetic samples that Dense layers generalize well, while CNN's convolutional filters are designed to exploit real morphological complexity that SMOTE partially flattens.

All experiments tracked with MLflow. Download `mlruns/` and run `mlflow ui` to explore runs interactively.

---

## Project Structure

```
ECG-Arrhythmia-Classification/
├── ANN_version.ipynb          # Original ANN baseline
├── ECG_Arrhythmia_Upgraded.ipynb  # Full experiment: ANN vs CNN vs LSTM
├── data/
│   └── mitdb_full/            # MIT-BIH records (.dat, .hea, .atr)
├── mlruns/                    # MLflow experiment logs
└── README.md
```

---

## Dataset

**Source:** [MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/) via PhysioNet

- 48 patient ECG recordings, sampled at **360 Hz**
- Each heartbeat extracted as a **360-sample window** (0.5s each side of R-peak)
- **102,608 beats** loaded across all 48 records
- **14 beat types** after filtering rare classes (< 6 samples) for SMOTE compatibility

| Symbol | Beat Type |
|--------|-----------|
| N | Normal sinus beat |
| V | Premature ventricular contraction |
| L | Left bundle branch block |
| R | Right bundle branch block |
| A | Atrial premature beat |
| F | Fusion beat |
| f | Fusion of paced + normal |
| j | Nodal escape beat |
| E | Ventricular escape |
| a | Aberrated atrial premature |
| J | Nodal premature beat |
| S | Supraventricular premature |
| Q | Unclassifiable |
| e | Atrial escape |

**Class imbalance (raw):** N class has 75,011 samples; rarest classes have < 10. Addressed with SMOTE + undersampling (see below).

---

## Pipeline

### 1. Signal Denoising — Discrete Wavelet Transform (DWT)
Raw ECG signals contain baseline wander, powerline interference, and high-frequency noise. DWT decomposes each beat into frequency bands using a **Daubechies-4 wavelet at 7 levels**. High-frequency detail coefficients (cD1–cD7) are soft-thresholded using the Donoho-Johnstone universal threshold:

```
threshold = σ × √(2 × log(n))
σ = median(|cD1|) / 0.6745
```

This preserves clinically relevant morphological features (P-wave, QRS complex, T-wave) while suppressing noise.

### 2. Class Imbalance — SMOTE + Undersampling
Raw data is heavily skewed (N dominates with 75,011 samples). Two-step balancing:
- **SMOTE** (k=5 neighbors): Synthetically oversamples all minority classes to 75,011 each
- **Undersample N**: Caps Normal class at 50,000 to prevent dominance

Final balanced dataset: **~1,025,143 samples** across 14 classes.

### 3. Train/Val/Test Split
Stratified 60/20/20 split:
- Train: 615,085 samples
- Val: 205,029 samples  
- Test: 205,029 samples

### 4. Architecture Comparison

**ANN (Baseline)**
```
Input(360) → Dense(256) → BatchNorm → Dropout(0.3)
           → Dense(128) → BatchNorm → Dropout(0.3)
           → Dense(64)  → Dropout(0.2)
           → Dense(14, softmax)
```
Parameters: 135,246 | Optimizer: Adam (lr=0.001) | Batch: 64

**1D-CNN**
```
Input(360,1) → Conv1D(64, k=5) → BatchNorm → MaxPool(2)
             → Conv1D(128, k=5) → BatchNorm → MaxPool(2)
             → Conv1D(256, k=3) → BatchNorm → GlobalAvgPool
             → Dense(128) → Dropout(0.4)
             → Dense(14, softmax)
```
Optimizer: Adam (lr=0.001) | Batch: 64

**LSTM**
```
Input(360,1) → LSTM(64, return_sequences=True) → Dropout(0.3)
             → LSTM(128) → Dropout(0.3)
             → Dense(64, relu)
             → Dense(14, softmax)
```
Optimizer: Adam (lr=0.001) | Batch: 128

### 5. Experiment Tracking — MLflow
All runs logged with:
- Hyperparameters (architecture, layers, dropout, batch size, learning rate)
- Test metrics (accuracy, F1 macro, F1 weighted)
- Confusion matrix artifacts
- Saved model files (.h5)

---

## Per-Class Performance (LSTM — Best Model)

| Class | Precision | Recall | F1 |
|-------|-----------|--------|----|
| 0 | 0.99 | 1.00 | 0.99 |
| 1 | 1.00 | 1.00 | 1.00 |
| 2 | 0.99 | 1.00 | 0.99 |
| 3–4 | 1.00 | 1.00 | 1.00 |
| 5 (N) | 0.99 | 0.97 | 0.98 |
| 6–13 | 1.00 | 1.00 | 1.00 |

Class 5 (Normal) has the lowest recall (0.97) across all models — a consistent finding likely due to undersampling N to 50,000 vs 75,011 for other classes.

---

## Key Findings

- **LSTM best overall** — sequential memory of the 360-sample beat gave it an edge even on SMOTE-augmented data
- **ANN beat CNN** — unexpected result explained by SMOTE: synthetic interpolated samples reduce the sharp waveform features that convolutional filters are designed to detect
- **Normal class hardest to classify** — consistent across all 3 architectures (recall ~96-97%), driven by undersampling
- **DWT denoising improves signal quality** — removes baseline wander and high-frequency noise while preserving P-QRS-T morphology
- **Per-class F1 is the honest metric** — not overall accuracy, which is inflated by the large balanced dataset

---

## Setup & Usage

### Requirements
```bash
pip install wfdb PyWavelets imbalanced-learn tensorflow mlflow scikit-learn seaborn numpy matplotlib
```

### Run the notebook
```bash
jupyter notebook ECG_Arrhythmia_Upgraded.ipynb
```

Update the data path in Cell 2 to point to your local MIT-BIH folder:
```python
record = wfdb.rdrecord(f'data/mitdb_full/{rec}')
annotation = wfdb.rdann(f'data/mitdb_full/{rec}', 'atr')
```

Or download directly from PhysioNet:
```python
record = wfdb.rdrecord(rec, pn_dir='mitdb')
annotation = wfdb.rdann(rec, 'atr', pn_dir='mitdb')
```

### View MLflow experiments
```bash
mlflow ui
```
Open `http://localhost:5000` to compare all 3 runs interactively.

---

## Hardware
Trained on **Kaggle P100 GPU** (16GB). Training times:
- ANN: ~27s/epoch
- CNN: ~70s/epoch  
- LSTM: ~248s/epoch (sequential architecture limits GPU parallelism)

---


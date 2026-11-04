"""
Central configuration for the ECG AI project.
Edit this file to change hyperparameters, paths, and model settings.
"""

from dataclasses import dataclass, field
from pathlib import Path
import torch


# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent

@dataclass
class PathConfig:
    root:        Path = ROOT
    data_dir:    Path = ROOT / "data" / "raw"
    processed:   Path = ROOT / "data" / "processed"
    checkpoints: Path = ROOT / "checkpoints"
    logs:        Path = ROOT / "logs"
    figures:     Path = ROOT / "figures"

    def make_dirs(self):
        for p in [self.data_dir, self.processed, self.checkpoints,
                  self.logs, self.figures]:
            p.mkdir(parents=True, exist_ok=True)


# ── Signal / Data ─────────────────────────────────────────────────────────────

@dataclass
class DataConfig:
    # WFDB / PhysioNet
    wfdb_db:        str   = "mitdb"
    physionet_url:  str   = "https://physionet.org/files/"

    # Hugging Face datasets
    hf_dataset:     str   = "sileod/ecg-arrhythmia"   # example

    # Signal properties
    fs:             int   = 360             # sampling frequency (Hz)
    leads:          list  = field(default_factory=lambda: ["MLII"])
    n_leads:        int   = 1

    # Preprocessing
    lowcut:         float = 0.5             # bandpass low  (Hz)
    highcut:        float = 40.0            # bandpass high (Hz)
    filter_order:   int   = 4

    # Segmentation
    segment_len:    int   = 1024            # samples per segment
    stride:         int   = 512             # overlap stride (samples)

    # Dataset splits
    train_ratio:    float = 0.70
    val_ratio:      float = 0.15
    # test = 1 - train - val

    # Classes (update for your task)
    num_classes:    int   = 5
    class_names:    list  = field(default_factory=lambda: [
        "N", "S", "V", "F", "Q"
    ])


# ── Model ─────────────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    # Patch embedding
    patch_len:   int   = 64             # samples per patch
    patch_stride: int  = 32

    # Transformer
    d_model:     int   = 128
    nhead:       int   = 8
    num_layers:  int   = 4
    dim_ff:      int   = 256
    dropout:     float = 0.1

    # Task head
    task:        str   = "classification"   # "classification" | "regression"
    num_classes: int   = 5                  # kept in sync with DataConfig


# ── Training ──────────────────────────────────────────────────────────────────

@dataclass
class TrainConfig:
    seed:          int   = 42
    epochs:        int   = 50
    batch_size:    int   = 64
    lr:            float = 1e-4
    weight_decay:  float = 1e-5

    # Scheduler
    scheduler:     str   = "cosine"         # "cosine" | "step" | "none"
    warmup_epochs: int   = 5
    eta_min:       float = 1e-6

    # Checkpointing
    save_every:    int   = 5                # epochs
    keep_best:     bool  = True

    # Logging
    log_interval:  int   = 10              # batches
    use_wandb:     bool  = False
    wandb_project: str   = "ecg-ai"


# ── Master config ─────────────────────────────────────────────────────────────

@dataclass
class Config:
    paths:  PathConfig  = field(default_factory=PathConfig)
    data:   DataConfig  = field(default_factory=DataConfig)
    model:  ModelConfig = field(default_factory=ModelConfig)
    train:  TrainConfig = field(default_factory=TrainConfig)

    @property
    def device(self) -> torch.device:
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def __post_init__(self):
        # Keep num_classes in sync between data and model configs
        self.model.num_classes = self.data.num_classes


# Singleton used project-wide
cfg = Config()

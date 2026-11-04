"""
General utilities: seeding, device, checkpoints, model info.
"""

import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


def set_seed(seed: int = 42):
    """Fix all random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark     = False


def get_device() -> torch.device:
    """Return the best available device."""
    if torch.cuda.is_available():
        dev = torch.device("cuda")
    elif torch.backends.mps.is_available():
        dev = torch.device("mps")
    else:
        dev = torch.device("cpu")
    print(f"Using device: {dev}")
    return dev


def count_parameters(model: nn.Module) -> int:
    """Count trainable parameters and print a summary."""
    total   = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Parameters — total: {total:,}  trainable: {trainable:,}")
    return trainable


def save_checkpoint(
    state: dict,
    path:  str | Path,
):
    """Save a generic state dict."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, path)
    print(f"Checkpoint saved → {path}")


def load_checkpoint(
    path:        str | Path,
    model:       nn.Module,
    optimizer=   None,
    device:      torch.device = None,
) -> dict:
    """Load model (and optionally optimizer) state from a checkpoint."""
    device = device or torch.device("cpu")
    ckpt   = torch.load(path, map_location=device)
    model.load_state_dict(ckpt["model"])
    if optimizer and "optimizer" in ckpt:
        optimizer.load_state_dict(ckpt["optimizer"])
    print(f"Loaded checkpoint from {path}")
    return ckpt

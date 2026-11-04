"""
PyTorch Dataset and DataLoader construction for ECG data.
"""

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader, random_split, WeightedRandomSampler
from typing import Optional, Callable

from config.config import cfg


class ECGDataset(Dataset):
    """
    Generic ECG dataset.

    Args:
        signals:   np.ndarray of shape (N, segment_len) or (N, segment_len, n_leads)
        labels:    np.ndarray of shape (N,) — int class indices
        transform: optional callable applied to each signal tensor
    """

    def __init__(
        self,
        signals: np.ndarray,
        labels: np.ndarray,
        transform: Optional[Callable] = None,
    ):
        assert len(signals) == len(labels), "signals and labels must have the same length"
        self.signals   = torch.from_numpy(signals.astype(np.float32))
        self.labels    = torch.from_numpy(labels.astype(np.int64))
        self.transform = transform

    def __len__(self) -> int:
        return len(self.signals)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        x = self.signals[idx]   # (segment_len,) or (segment_len, n_leads)
        y = self.labels[idx]

        # Transformer expects (seq_len, features) — add channel dim if 1-D
        if x.ndim == 1:
            x = x.unsqueeze(-1)   # (segment_len, 1)

        if self.transform is not None:
            x = self.transform(x)

        return x, y

    @property
    def class_weights(self) -> torch.Tensor:
        """Inverse-frequency weights for WeightedRandomSampler or loss weighting."""
        counts = torch.bincount(self.labels, minlength=cfg.data.num_classes).float()
        weights = 1.0 / (counts + 1e-8)
        weights /= weights.sum()
        return weights


def build_dataloaders(
    dataset: ECGDataset,
    train_ratio: float = None,
    val_ratio:   float = None,
    batch_size:  int   = None,
    num_workers: int   = 0,
    weighted_sampling: bool = False,
    seed: int = None,
) -> tuple[DataLoader, DataLoader, DataLoader]:
    """
    Split a dataset into train / val / test DataLoaders.

    Args:
        dataset:           ECGDataset to split
        train_ratio:       fraction of data for training (default cfg.data.train_ratio)
        val_ratio:         fraction of data for validation (default cfg.data.val_ratio)
        batch_size:        (default cfg.train.batch_size)
        num_workers:       DataLoader workers
        weighted_sampling: use class-balanced sampling for train loader
        seed:              random seed for the split

    Returns:
        train_loader, val_loader, test_loader
    """
    train_ratio = train_ratio or cfg.data.train_ratio
    val_ratio   = val_ratio   or cfg.data.val_ratio
    batch_size  = batch_size  or cfg.train.batch_size
    seed        = seed        or cfg.train.seed

    n = len(dataset)
    n_train = int(n * train_ratio)
    n_val   = int(n * val_ratio)
    n_test  = n - n_train - n_val

    generator = torch.Generator().manual_seed(seed)
    train_ds, val_ds, test_ds = random_split(
        dataset, [n_train, n_val, n_test], generator=generator
    )

    if weighted_sampling:
        class_w  = dataset.class_weights
        sample_w = class_w[dataset.labels[train_ds.indices]]
        sampler  = WeightedRandomSampler(sample_w, num_samples=len(train_ds), replacement=True)
        train_loader = DataLoader(train_ds, batch_size=batch_size,
                                  sampler=sampler, num_workers=num_workers)
    else:
        train_loader = DataLoader(train_ds, batch_size=batch_size,
                                  shuffle=True, num_workers=num_workers)

    val_loader  = DataLoader(val_ds,  batch_size=batch_size, shuffle=False, num_workers=num_workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    return train_loader, val_loader, test_loader

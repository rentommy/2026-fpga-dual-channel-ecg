"""
Visualization utilities for ECG signals and training diagnostics.
All functions accept either numpy arrays or torch tensors.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.metrics import ConfusionMatrixDisplay

from config.config import cfg


def _to_numpy(x) -> np.ndarray:
    import torch
    if isinstance(x, torch.Tensor):
        return x.cpu().numpy()
    return np.asarray(x)


# ── ECG signal plots ───────────────────────────────────────────────────────────

def plot_ecg(
    signal:    np.ndarray,
    fs:        int            = None,
    lead_names: list          = None,
    title:     str            = "ECG Signal",
    r_peaks:   Optional[np.ndarray] = None,
    save_path: Optional[Path] = None,
):
    """
    Plot one or more ECG leads stacked vertically.

    Args:
        signal:     (n_samples,) or (n_samples, n_leads)
        fs:         sampling frequency in Hz
        lead_names: list of lead names, e.g. ["I","II","V1",…]
        r_peaks:    sample indices to mark as R-peaks
        save_path:  if given, saves the figure to this path
    """
    signal    = _to_numpy(signal)
    fs        = fs or cfg.data.fs
    lead_names = lead_names or cfg.data.leads

    if signal.ndim == 1:
        signal = signal[:, None]

    n_samples, n_leads = signal.shape
    time = np.arange(n_samples) / fs

    fig, axes = plt.subplots(n_leads, 1, figsize=(14, 2.5 * n_leads), sharex=True)
    if n_leads == 1:
        axes = [axes]

    for i, ax in enumerate(axes):
        ax.plot(time, signal[:, i], linewidth=0.8, color="royalblue")
        if r_peaks is not None:
            ax.scatter(r_peaks / fs, signal[r_peaks, i], color="red",
                       s=30, zorder=5, label="R-peaks")
        ax.set_ylabel(lead_names[i] if i < len(lead_names) else f"Lead {i+1}")
        ax.grid(True, alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)

    axes[-1].set_xlabel("Time (s)")
    fig.suptitle(title, fontsize=14)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
    return fig


def plot_beat_overlay(
    beats:     np.ndarray,
    fs:        int   = None,
    label:     str   = "Beat overlay",
    save_path: Optional[Path] = None,
):
    """
    Overlay multiple beat waveforms (e.g. from one class) on a single axis.

    Args:
        beats: (n_beats, beat_len) numpy array
    """
    beats = _to_numpy(beats)
    fs    = fs or cfg.data.fs
    t     = np.arange(beats.shape[1]) / fs * 1000   # ms

    fig, ax = plt.subplots(figsize=(8, 4))
    for beat in beats:
        ax.plot(t, beat, alpha=0.3, linewidth=0.7, color="royalblue")
    ax.plot(t, beats.mean(axis=0), color="black", linewidth=2, label="Mean")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Amplitude (mV)")
    ax.set_title(label)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
    return fig


# ── Training diagnostics ───────────────────────────────────────────────────────

def plot_training_curves(
    history:   dict,
    save_path: Optional[Path] = None,
):
    """
    Plot loss and accuracy curves from a training history dict.

    Args:
        history: dict with keys "train_loss", "val_loss", "train_acc", "val_acc"
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    epochs = range(1, len(history["train_loss"]) + 1)

    ax1.plot(epochs, history["train_loss"], label="Train")
    ax1.plot(epochs, history["val_loss"],   label="Val")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Loss")
    ax1.set_title("Loss")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    if "train_acc" in history:
        ax2.plot(epochs, history["train_acc"], label="Train")
        ax2.plot(epochs, history["val_acc"],   label="Val")
        ax2.set_xlabel("Epoch")
        ax2.set_ylabel("Accuracy")
        ax2.set_title("Accuracy")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
    return fig


def plot_confusion_matrix(
    cm:          np.ndarray,
    class_names: list = None,
    title:       str  = "Confusion Matrix",
    save_path:   Optional[Path] = None,
):
    """
    Plot a confusion matrix using sklearn's ConfusionMatrixDisplay.

    Args:
        cm:          confusion matrix (num_classes × num_classes)
        class_names: list of label strings
    """
    class_names = class_names or cfg.data.class_names
    disp = ConfusionMatrixDisplay(cm, display_labels=class_names)
    fig, ax = plt.subplots(figsize=(8, 8))
    disp.plot(ax=ax, colorbar=True, cmap="Blues")
    ax.set_title(title)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
    return fig


def plot_attention_weights(
    attn_weights: np.ndarray,
    title:        str  = "Attention Weights",
    save_path:    Optional[Path] = None,
):
    """
    Visualise a (heads, seq_len, seq_len) attention weight tensor.
    Plots one heatmap per head.
    """
    attn_weights = _to_numpy(attn_weights)
    if attn_weights.ndim == 2:
        attn_weights = attn_weights[None]   # add head dim

    n_heads = attn_weights.shape[0]
    fig, axes = plt.subplots(1, n_heads, figsize=(4 * n_heads, 4))
    if n_heads == 1:
        axes = [axes]

    for i, ax in enumerate(axes):
        im = ax.imshow(attn_weights[i], aspect="auto", cmap="viridis")
        ax.set_title(f"Head {i+1}")
        fig.colorbar(im, ax=ax)

    fig.suptitle(title)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
    return fig

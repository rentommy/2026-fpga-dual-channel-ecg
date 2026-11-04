"""
Evaluation metrics for ECG classification and regression.
"""

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)
from typing import Optional


def compute_metrics(
    preds: torch.Tensor | np.ndarray,
    targets: torch.Tensor | np.ndarray,
    num_classes: int = 2,
    average: str = "macro",
) -> dict:
    """
    Compute standard classification metrics.

    Args:
        preds:       (N,) predicted class indices  OR  (N, C) logits/probabilities
        targets:     (N,) ground-truth class indices
        num_classes: number of classes
        average:     "macro" | "micro" | "weighted" for F1 / AUC

    Returns:
        dict with keys: accuracy, f1, auc, confusion_matrix
    """
    # Convert to numpy
    if isinstance(preds, torch.Tensor):
        preds = preds.cpu().numpy()
    if isinstance(targets, torch.Tensor):
        targets = targets.cpu().numpy()

    # If preds are logits/probabilities, get class labels and keep probs for AUC
    if preds.ndim == 2:
        probs      = preds
        pred_labels = preds.argmax(axis=1)
    else:
        pred_labels = preds.astype(int)
        probs       = None

    acc = accuracy_score(targets, pred_labels)
    f1  = f1_score(targets, pred_labels, average=average, zero_division=0)

    auc = None
    if probs is not None:
        try:
            if num_classes == 2:
                auc = roc_auc_score(targets, probs[:, 1])
            else:
                auc = roc_auc_score(
                    targets, probs,
                    multi_class="ovr",
                    average=average,
                )
        except ValueError:
            auc = float("nan")

    cm = confusion_matrix(targets, pred_labels, labels=list(range(num_classes)))

    return {
        "accuracy":         acc,
        "f1":               f1,
        "auc":              auc,
        "confusion_matrix": cm,
    }


def compute_regression_metrics(
    preds: torch.Tensor | np.ndarray,
    targets: torch.Tensor | np.ndarray,
) -> dict:
    """MAE, MSE, RMSE, R² for regression tasks."""
    if isinstance(preds, torch.Tensor):
        preds = preds.cpu().numpy().squeeze()
    if isinstance(targets, torch.Tensor):
        targets = targets.cpu().numpy().squeeze()

    mae  = np.abs(preds - targets).mean()
    mse  = ((preds - targets) ** 2).mean()
    rmse = np.sqrt(mse)

    ss_res = ((targets - preds) ** 2).sum()
    ss_tot = ((targets - targets.mean()) ** 2).sum()
    r2 = 1 - ss_res / (ss_tot + 1e-8)

    return {"mae": mae, "mse": mse, "rmse": rmse, "r2": r2}


def print_classification_report(
    preds:   np.ndarray,
    targets: np.ndarray,
    class_names: Optional[list] = None,
):
    print(classification_report(targets, preds, target_names=class_names, zero_division=0))

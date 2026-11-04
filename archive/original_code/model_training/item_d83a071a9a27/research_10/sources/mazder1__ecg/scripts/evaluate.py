"""
CLI evaluation script.

Usage:
    python scripts/evaluate.py --checkpoint checkpoints/best.pt

Loads a checkpoint, runs inference on the test set,
and prints + saves metrics and a confusion matrix.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import torch

from config.config import cfg
from data.dataset import ECGDataset, build_dataloaders
from data.loader import load_mitbih_dataset
from models.ecg_cnntransformers import build_model
from training.metrics import compute_metrics, print_classification_report
from utils.helpers import set_seed, load_checkpoint
from utils.visualization import plot_confusion_matrix


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate ECG Transformer")
    parser.add_argument("--checkpoint", type=str, required=True,
                        help="Path to .pt checkpoint file")
    parser.add_argument("--task",       type=str, default=cfg.model.task)
    parser.add_argument("--seed",       type=int, default=cfg.train.seed)
    return parser.parse_args()


@torch.no_grad()
def run_inference(model, loader, device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    all_logits, all_targets = [], []
    for x, y in loader:
        x = x.to(device)
        logits = model(x)
        all_logits.append(logits.cpu().numpy())
        all_targets.append(y.numpy())
    return np.concatenate(all_logits), np.concatenate(all_targets)


def main():
    args = parse_args()
    set_seed(args.seed)
    cfg.model.task = args.task

    # ── Data ──────────────────────────────────────────────────────────────────
    # Use the same seed as training so the split is identical → unseen test set
    print("Loading MIT-BIH data …")
    signals, labels = load_mitbih_dataset()
    dataset = ECGDataset(signals, labels)
    _, _, test_loader = build_dataloaders(dataset)

    # ── Model ─────────────────────────────────────────────────────────────────
    model = build_model(task=args.task)
    load_checkpoint(args.checkpoint, model, device=cfg.device)
    model.to(cfg.device)

    # ── Inference ─────────────────────────────────────────────────────────────
    logits, targets = run_inference(model, test_loader, cfg.device)
    metrics = compute_metrics(logits, targets, num_classes=cfg.model.num_classes)

    print(f"\nTest Accuracy : {metrics['accuracy']:.4f}")
    print(f"Test F1       : {metrics['f1']:.4f}")
    if metrics["auc"] is not None:
        print(f"Test AUC      : {metrics['auc']:.4f}")

    print("\nClassification Report:")
    print_classification_report(
        logits.argmax(axis=1), targets,
        class_names=cfg.data.class_names,
    )

    cfg.paths.make_dirs()
    plot_confusion_matrix(
        metrics["confusion_matrix"],
        save_path=cfg.paths.figures / "confusion_matrix.png",
    )


if __name__ == "__main__":
    main()

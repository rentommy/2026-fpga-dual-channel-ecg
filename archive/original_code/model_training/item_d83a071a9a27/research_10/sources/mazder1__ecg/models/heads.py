"""
Task-specific output heads attached to the ECGTransformer backbone.
"""

import torch
import torch.nn as nn

from config.config import cfg


class ClassificationHead(nn.Module):
    """
    Multi-layer classification head.

    Input:  (B, d_model)
    Output: (B, num_classes)  — raw logits
    """

    def __init__(
        self,
        d_model:     int = None,
        num_classes: int = None,
        dropout:     float = None,
    ):
        super().__init__()
        d_model     = d_model     or cfg.model.d_model
        num_classes = num_classes or cfg.model.num_classes
        dropout     = dropout     or cfg.model.dropout

        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Dropout(dropout),
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)


class RegressionHead(nn.Module):
    """
    Single-value regression head.

    Input:  (B, d_model)
    Output: (B, 1)
    """

    def __init__(
        self,
        d_model: int   = None,
        dropout: float = None,
    ):
        super().__init__()
        d_model = d_model or cfg.model.d_model
        dropout = dropout or cfg.model.dropout

        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Dropout(dropout),
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Linear(d_model // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)


class MultiLabelHead(nn.Module):
    """
    Multi-label classification head (sigmoid output, not softmax).
    Useful for 12-lead ECG where multiple abnormalities may co-occur.

    Input:  (B, d_model)
    Output: (B, num_classes)  — probabilities in [0, 1]
    """

    def __init__(
        self,
        d_model:     int   = None,
        num_classes: int   = None,
        dropout:     float = None,
    ):
        super().__init__()
        d_model     = d_model     or cfg.model.d_model
        num_classes = num_classes or cfg.model.num_classes
        dropout     = dropout     or cfg.model.dropout

        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Dropout(dropout),
            nn.Linear(d_model, num_classes),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)

"""
CNN + Transformer model for ECG analysis.

Architecture:
  ECG signal → CNNBackbone (local feature extraction)
             → Linear projection → Positional Encoding
             → Transformer Encoder → mean pooling
             → task head (see heads.py)
"""

import torch
import torch.nn as nn

from config.config import cfg


class CNNBackbone(nn.Module):
    """
    Two-layer 1D CNN for local ECG feature extraction.

    Input:  (B, T, C)  — batch, time steps, leads
    Output: (B, T//8, 64)
    """

    def __init__(self, n_leads: int = None):
        super().__init__()
        n_leads = n_leads or cfg.data.n_leads

        self.conv1 = nn.Conv1d(n_leads, 32, kernel_size=5, padding="same")
        self.conv2 = nn.Conv1d(32, 64, kernel_size=5, padding="same")
        self.pool1 = nn.MaxPool1d(kernel_size=4)
        self.pool2 = nn.MaxPool1d(kernel_size=2)
        self.norm1 = nn.BatchNorm1d(32)
        self.norm2 = nn.BatchNorm1d(64)
        self.relu  = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, C) → transpose to (B, C, T) for Conv1d
        x = x.transpose(1, 2)
        x = self.pool1(self.relu(self.norm1(self.conv1(x))))  # (B, 32, T//4)
        x = self.pool2(self.relu(self.norm2(self.conv2(x))))  # (B, 64, T//8)
        x = x.transpose(1, 2)                                  # (B, T//8, 64)
        return x


class TransformerECG(nn.Module):
    """
    CNN backbone + Transformer encoder for ECG analysis.

    Input:  (B, T, C)  — raw segments (time, leads)
    Output: (B, d_model)  — mean-pooled representation

    All hyperparameters default to cfg.model / cfg.data.
    """

    def __init__(
        self,
        n_leads:    int   = None,
        d_model:    int   = None,
        nhead:      int   = None,
        num_layers: int   = None,
        dim_ff:     int   = None,
        dropout:    float = None,
    ):
        super().__init__()
        n_leads    = n_leads    or cfg.data.n_leads
        d_model    = d_model    or cfg.model.d_model
        nhead      = nhead      or cfg.model.nhead
        num_layers = num_layers or cfg.model.num_layers
        dim_ff     = dim_ff     or cfg.model.dim_ff
        dropout    = dropout    or cfg.model.dropout

        self.backbone   = CNNBackbone(n_leads)
        self.projection = nn.Linear(64, d_model)

        # Learnable positional encoding — sized to expected sequence length
        # pool1(4) × pool2(2) = 8× downsampling
        max_seq_len = cfg.data.segment_len // 8
        self.pos_encoding = nn.Parameter(torch.zeros(1, max_seq_len, d_model))
        nn.init.trunc_normal_(self.pos_encoding, std=0.02)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_ff,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers,
            norm=nn.LayerNorm(d_model),
        )

        self.d_model = d_model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.backbone(x)                       # (B, T//8, 64)
        x = self.projection(x)                     # (B, T//8, d_model)
        x = x + self.pos_encoding[:, :x.size(1)]  # positional encoding
        x = self.transformer(x)                    # (B, T//8, d_model)
        x = x.mean(dim=1)                          # (B, d_model)
        return x


def build_model(task: str = None) -> nn.Module:
    """
    Factory that returns a complete CNNTransformer + head.

    Args:
        task: "classification" | "regression" | "multilabel"
              (default cfg.model.task)

    Returns:
        nn.Sequential(backbone, head)
    """
    from models.heads import ClassificationHead, RegressionHead, MultiLabelHead

    task     = task or cfg.model.task
    backbone = TransformerECG()

    if task == "classification":
        head = ClassificationHead(backbone.d_model, cfg.model.num_classes)
    elif task == "regression":
        head = RegressionHead(backbone.d_model)
    elif task == "multilabel":
        head = MultiLabelHead(backbone.d_model, cfg.model.num_classes)
    else:
        raise ValueError(f"Unknown task: {task!r}")

    return nn.Sequential(backbone, head)

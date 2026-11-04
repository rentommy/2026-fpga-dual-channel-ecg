import torch
from torch import nn

class Residual(nn.Module):

    def __init__(self, a, b, d):
        super().__init__()
        self.net = nn.Sequential(nn.Conv1d(a, b, 5, padding=2 * d, dilation=d), nn.GroupNorm(4, b), nn.ReLU(), nn.Conv1d(b, b, 5, padding=2), nn.GroupNorm(4, b))
        self.skip = nn.Conv1d(a, b, 1) if a != b else nn.Identity()

    def forward(self, x):
        return torch.relu(self.net(x) + self.skip(x))

class Network(nn.Module):

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        if kind == 'baseline':
            self.base = BeatModel('se_gru')
            return
        if kind == 'multi':
            self.branches = nn.ModuleList([nn.Conv1d(2, 16, k, padding=k // 2) for k in [5, 15, 31]])
            self.body = nn.Sequential(Residual(48, 32, 1), Residual(32, 64, 2), Residual(64, 128, 4))
            self.gate = nn.Sequential(nn.Linear(128, 16), nn.ReLU(), nn.Linear(16, 128), nn.Sigmoid())
            channels = 128
        else:
            self.templates = nn.Conv1d(1, 28, 41, padding=20, bias=False)
            channels = 28
        self.rr = nn.Sequential(nn.Linear(8, 16), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(channels + 16, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 7))

    def forward(self, x, r):
        if self.kind == 'baseline':
            return self.base(x, r)
        mask = x[:, 1:2]
        if self.kind == 'multi':
            z = self.body(torch.cat([torch.relu(b(x)) for b in self.branches], 1))
            pooled = (z * mask).sum(-1) / mask.sum(-1).clamp_min(1)
            pooled = pooled * self.gate(pooled)
        else:
            z = torch.relu(self.templates(x[:, :1]))
            pooled = z.masked_fill(mask == 0, -1000000000.0).amax(-1)
        return self.head(torch.cat([pooled, self.rr(r)], 1))

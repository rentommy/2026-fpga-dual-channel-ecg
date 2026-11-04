import torch
from torch import nn

class AlignedCNN(nn.Module):
    """Position-preserving small CNN; channel 0 waveform, channel 1 validity mask."""
    def __init__(self,use_rr=False):
        super().__init__();self.use_rr=use_rr
        self.conv=nn.Sequential(nn.Conv1d(2,16,11,2,5),nn.GroupNorm(4,16),nn.SiLU(),
          nn.Conv1d(16,32,7,2,3),nn.GroupNorm(4,32),nn.SiLU(),
          nn.Conv1d(32,48,5,2,2),nn.GroupNorm(4,48),nn.SiLU(),nn.Flatten(),
          nn.Linear(48*36,96),nn.LayerNorm(96),nn.SiLU(),nn.Dropout(.2))
        self.timing=nn.Sequential(nn.Linear(8,16),nn.SiLU()) if use_rr else None
        self.head=nn.Sequential(nn.Linear(112 if use_rr else 96,64),nn.SiLU(),nn.Dropout(.2),nn.Linear(64,9))
    def forward(self,x,rr):
        h=self.conv(x)
        if self.use_rr:h=torch.cat([h,self.timing(rr)],dim=1)
        return self.head(h)

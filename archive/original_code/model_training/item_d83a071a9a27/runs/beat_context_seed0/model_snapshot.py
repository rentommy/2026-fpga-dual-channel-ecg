"""Shared residual morphology encoder + three-beat context + explicit RR branch."""
import torch
from torch import nn

class Residual(nn.Module):
    def __init__(self,ci,co,k,stride=1):
        super().__init__()
        self.body=nn.Sequential(nn.Conv1d(ci,co,k,stride,padding=k//2,bias=False),nn.GroupNorm(4,co),nn.SiLU(),
                                nn.Conv1d(co,co,5,padding=2,bias=False),nn.GroupNorm(4,co))
        self.skip=nn.Conv1d(ci,co,1,stride,bias=False) if ci!=co or stride!=1 else nn.Identity()
        self.act=nn.SiLU()
    def forward(self,x):return self.act(self.body(x)+self.skip(x))

class BeatContextNet(nn.Module):
    def __init__(self,classes=9,center_only=False):
        super().__init__()
        self.center_only=center_only
        self.encoder=nn.Sequential(nn.Conv1d(1,16,11,stride=2,padding=5,bias=False),nn.GroupNorm(4,16),nn.SiLU(),
          Residual(16,24,9,2),Residual(24,48,7,2),Residual(48,64,5,2),nn.AdaptiveAvgPool1d(1),nn.Flatten())
        self.rr=nn.Sequential(nn.Linear(8,32),nn.LayerNorm(32),nn.SiLU(),nn.Dropout(.1),nn.Linear(32,32),nn.SiLU())
        # Center embedding has its own position; never average labels over context.
        self.head=nn.Sequential(nn.Linear(64 if center_only else 64*3+32,96),nn.LayerNorm(96),nn.SiLU(),nn.Dropout(.25),nn.Linear(96,classes))
    def forward(self,wave,rr):
        if self.center_only:return self.head(self.encoder(wave[:,1:2,:]))
        b=wave.shape[0];features=self.encoder(wave.reshape(b*3,1,256)).reshape(b,3*64)
        return self.head(torch.cat([features,self.rr(rr)],dim=1))

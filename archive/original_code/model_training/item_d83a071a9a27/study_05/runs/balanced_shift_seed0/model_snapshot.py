import torch
from torch import nn

class SE(nn.Module):
    def __init__(self,c):
        super().__init__()
        self.gate=nn.Sequential(nn.Linear(c,max(2,c//16),bias=False),nn.ReLU(),nn.Linear(max(2,c//16),c,bias=False),nn.Hardsigmoid())
    def forward(self,x):return x*self.gate(x.mean(-1)).unsqueeze(-1)

class BeatModel(nn.Module):
    """Adaptation of source CNN/GRU/SE ideas to 288-point central beats."""
    def __init__(self,kind):
        super().__init__();self.kind=kind
        blocks=[]
        for a,b,k in [(2,16,11),(16,32,7),(32,48,5)]:
            blocks.extend([nn.Conv1d(a,b,k,padding=k//2),nn.GroupNorm(4,b),nn.ReLU()])
            if kind=='se_gru':blocks.append(SE(b))
            blocks.append(nn.MaxPool1d(2))
        self.conv=nn.Sequential(*blocks)
        self.temporal=nn.GRU(48,24,batch_first=True) if kind!='cnn' else None
        self.morph=nn.Sequential(nn.Linear(24 if self.temporal else 48*36,64),nn.ReLU(),nn.Dropout(.2))
        self.rr=nn.Sequential(nn.Linear(8,16),nn.ReLU())
        self.head=nn.Linear(80,7)
    def forward(self,x,rr):
        z=self.conv(x)
        z=self.temporal(z.transpose(1,2))[1][-1] if self.temporal else z.flatten(1)
        return self.head(torch.cat([self.morph(z),self.rr(rr)],1))

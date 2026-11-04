"""SENetLSTM.py 的 PyTorch 版本。

与 TensorFlow 版逐层核对过：'same' padding 的补零量、BatchNorm 的 eps/momentum、
hard_sigmoid 的公式、LSTM 的初始化方式，详见各处注释。
注意 PyTorch 的 Conv1d 是 (N, C, L)，通道维在中间，和 TF 的 (N, L, C) 不同。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def same_pad(length, kernel, stride):
    """复现 TF 'SAME' 的补零量：多出来的那一格补在右边。PyTorch 的 padding='same' 不支持 stride>1。"""
    out = -(-length // stride)                       # ceil(length / stride)
    total = max((out - 1) * stride + kernel - length, 0)
    return total // 2, total - total // 2


class SEBlock(nn.Module):
    """对应 SENetLSTM.py 的 SEBlock：两个无 bias 的全连接，relu -> hard_sigmoid，再逐通道相乘。"""

    def __init__(self, channels, reduction=16):
        super().__init__()
        self.fc1 = nn.Linear(channels, channels // reduction, bias=False)
        self.fc2 = nn.Linear(channels // reduction, channels, bias=False)

    def forward(self, x):                            # x: (N, C, L)
        w = x.mean(dim=2)                            # GlobalAveragePooling1D
        w = F.relu(self.fc1(w))
        w = F.hardsigmoid(self.fc2(w))               # 与 Keras 3 的 hard_sigmoid 公式一致: relu6(x+3)/6
        return x * w.unsqueeze(2)


class SENetLSTM(nn.Module):
    """对应 SENetLSTM.py 的 SENet_LSTM()。输入 (N, 1, 3600)，输出 (N, num_classes) 的 logits。"""

    def __init__(self, num_classes=7, in_length=3600):
        super().__init__()
        self.in_length = in_length
        # Keras BatchNormalization 默认 momentum=0.99 / epsilon=1e-3；
        # PyTorch 的 momentum 定义是反的（running = (1-m)*running + m*batch），所以 0.99 对应 0.01
        self.conv1 = nn.Conv1d(1, 128, kernel_size=20, stride=3)
        self.bn1 = nn.BatchNorm1d(128, eps=1e-3, momentum=0.01)
        self.conv2 = nn.Conv1d(128, 32, kernel_size=7, stride=1)
        self.se1 = SEBlock(32)
        self.bn2 = nn.BatchNorm1d(32, eps=1e-3, momentum=0.01)
        self.conv3 = nn.Conv1d(32, 32, kernel_size=10, stride=1)
        self.se2 = SEBlock(32)
        self.lstm = nn.LSTM(32, 10, batch_first=True)
        self.drop = nn.Dropout(0.1)
        self.fc1 = nn.Linear(10, 20)
        self.fc2 = nn.Linear(20, 10)
        self.fc3 = nn.Linear(10, num_classes)
        self._init_like_keras()

    def _init_like_keras(self):
        """Keras 默认 glorot_uniform + bias 全 0；PyTorch 默认是 kaiming_uniform，这里对齐。"""
        for m in self.modules():
            if isinstance(m, (nn.Conv1d, nn.Linear)):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
        for name, p in self.lstm.named_parameters():
            if 'weight_ih' in name:
                nn.init.xavier_uniform_(p)
            elif 'weight_hh' in name:
                nn.init.orthogonal_(p)               # Keras recurrent_initializer='orthogonal'
            elif 'bias' in name:
                nn.init.zeros_(p)
        # Keras 的 unit_forget_bias=True：遗忘门 bias 初始化为 1（PyTorch 门序也是 i,f,g,o）
        hidden = self.lstm.hidden_size
        self.lstm.bias_ih_l0.data[hidden:2 * hidden] = 1.0

    def forward(self, x):                            # x: (N, 1, 3600)
        L = self.in_length
        x = F.pad(x, same_pad(L, 20, 3))             # (8, 9)
        x = F.relu(self.conv1(x))                    # -> (N, 128, 1200)
        x = self.bn1(x)
        x = F.max_pool1d(x, kernel_size=2, stride=3)  # -> (N, 128, 400)
        x = F.pad(x, same_pad(x.shape[2], 7, 1))     # (3, 3)
        x = F.relu(self.conv2(x))                    # -> (N, 32, 400)
        x = self.se1(x)
        x = self.bn2(x)
        x = F.max_pool1d(x, kernel_size=2, stride=2)  # -> (N, 32, 200)
        x = F.pad(x, same_pad(x.shape[2], 10, 1))    # (4, 5)
        x = F.relu(self.conv3(x))                    # -> (N, 32, 200)
        x = self.se2(x)
        x = F.max_pool1d(x, kernel_size=2, stride=2)  # -> (N, 32, 100)
        x = x.transpose(1, 2)                        # LSTM 要 (N, L, C)
        out, _ = self.lstm(x)
        x = out[:, -1, :]                            # Keras LSTM 默认只返回最后一个时间步
        x = self.drop(x)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)                           # 返回 logits，softmax 交给损失函数/推理时再做

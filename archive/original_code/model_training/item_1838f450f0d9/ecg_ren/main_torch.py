"""
main.py 的 PyTorch 版本，用于在有独立显卡的机器上加速训练。

与 TensorFlow 版的对应关系已逐层核对（padding 补零量、BatchNorm 的 eps/momentum、
hard_sigmoid 公式、class_weight 的归一化方式、validation_split 的切分位置），
详见各处注释。路径不再写死，默认用本脚本所在目录，方便换机器直接跑。
"""
import argparse
import datetime
import os
import time

import matplotlib
matplotlib.use('Agg')                  # 不弹窗，直接存图（和改过的 main.py 保持一致）
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

import torch
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter

from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import confusion_matrix
from sklearn import preprocessing

# 调用模型架构
from model.SENetLSTM_torch import SENetLSTM


# ===================================================命令行参数==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description='ECG 分类 (SENet + LSTM) PyTorch 版')
parser.add_argument('--data-dir', default=os.path.join(BASE_DIR, 'Data'), help='csv 数据目录')
parser.add_argument('--out-dir', default=BASE_DIR, help='日志/模型/曲线的输出根目录')
parser.add_argument('--epochs', type=int, default=60)
parser.add_argument('--batch-size', type=int, default=32,
                    help='默认 32 与 TF 版一致；GPU 上调到 256 能快好几倍，但会改变训练动态')
parser.add_argument('--lr', type=float, default=0.001)
parser.add_argument('--device', default=None, help='cuda / cpu，默认自动选择')
parser.add_argument('--no-amp', action='store_true', help='关闭混合精度（默认在 CUDA 上开启）')
parser.add_argument('--no-gpu-cache', action='store_true',
                    help='不要把整个数据集常驻显存（显存不足时加这个）')
parser.add_argument('--seed', type=int, default=0)
args = parser.parse_args()

torch.manual_seed(args.seed)
np.random.seed(args.seed)

device = torch.device(args.device) if args.device else torch.device('cuda' if torch.cuda.is_available() else 'cpu')
use_amp = (device.type == 'cuda') and not args.no_amp
print(f'device: {device}')
if device.type == 'cuda':
    print(f'GPU: {torch.cuda.get_device_name(0)}  '
          f'显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB  '
          f'torch: {torch.__version__} (cuda {torch.version.cuda})')
    torch.backends.cudnn.benchmark = True      # 输入尺寸固定，让 cuDNN 自动挑最快的卷积算法
else:
    print(f'torch: {torch.__version__}  ——  没检测到可用 GPU，将在 CPU 上训练（很慢）')


# ===================================================读取数据==================================================
print('load data...')
path = args.data_dir + os.sep
X_list = [
    path + '0MLIIIecg_data.csv',
    path + '1MLIIecg_data.csv',
    path + '2ECGecg_data.csv',
    path + '3ECGecg_data.csv']

Y_list = [
    path + '0MLIIIsymbols_data.csv',
    path + '1MLIIsymbols_data.csv',
    path + '2ECGsymbols_data.csv',
    path + '3ECGsymbols_data.csv']

print('begin concatenating...')

# 直接按 float32 读取：不要用 dtype="str" 再转，字符串中间数组会占用近 4 倍内存（单个文件就要 6GB+）
X_parts = []
for i in tqdm(range(0, len(X_list)), desc='处理记录'):
    X_parts.append(np.loadtxt(X_list[i], delimiter=',', skiprows=1).astype('float32'))
X = np.concatenate(X_parts)        # 一次性拼接，避免循环里反复复制
del X_parts

Y_parts = []
for i in tqdm(range(0, len(Y_list)), desc='处理记录'):
    Y_parts.append(np.loadtxt(Y_list[i], dtype='str', delimiter=',', skiprows=1))
Y = np.concatenate(Y_parts)
del Y_parts

print('X shape:', X.shape)   # 应该是 (总样本数, 3600)
print('Y shape:', Y.shape)

keep = Y != 'Q'                # 删除Q（布尔掩码比 np.delete 省一次大数组复制）
X = X[keep]
Y = Y[keep]

# 每样本去直流 + 标准化（减均值、除标准差，去掉电极直流偏置）
# 原地运算，避免生成两份 1.7GB 的临时副本
X -= X.mean(axis=1, keepdims=True)
X /= (X.std(axis=1, keepdims=True) + 1e-8)
X = np.expand_dims(X, axis=1)    # PyTorch 的 Conv1d 是 (N, C, L)，通道维在中间，和 TF 的 (N, L, C) 不同

# 把标签编码
AAMI = ['N', 'L', 'R', 'V', 'A', '|', 'B']
NUM_CLASSES = len(AAMI)
le = preprocessing.LabelEncoder()                          # 标签字符变编码
le = le.fit(AAMI)
Y = le.transform(Y)

sss = StratifiedShuffleSplit(n_splits=1, test_size=0.1, train_size=0.9, random_state=0)   # 1:9分割测试集和训练集
for train_index, test_index in sss.split(X, Y):
    X_train, X_test = X[train_index], X[test_index]
    y_train, y_test = Y[train_index], Y[test_index]

del X, Y      # 训练集/测试集已复制出来，释放整份数据占用的内存

# Keras 的 validation_split=0.2 是「不打乱、直接取最后 20%」，这里照抄同样的切法
split_at = int(len(X_train) * (1 - 0.2))
X_val, y_val = X_train[split_at:], y_train[split_at:]
X_train, y_train = X_train[:split_at], y_train[:split_at]
print(f'train: {X_train.shape}, val: {X_val.shape}, test: {X_test.shape}')


# ===================================================构建模型==================================================
model = SENetLSTM(num_classes=NUM_CLASSES).to(device)
n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f'trainable params: {n_params:,}')
print(model)


# ===================================================训练准备==================================================
# 类别权重：少数类给大权重，缓解数据不平衡（N 占96% 给小权重）
# 注意 LabelEncoder 是按字母序编码的（A=0,B=1,L=2,N=3,R=4,V=5,|=6），不是上面 AAMI 列表的顺序，
# 所以这里按标签名去查编号，不能写死数字，否则权重会加到错误的类别上
weight_by_symbol = {'N': 0.1, 'L': 1.0, 'R': 1.0, 'V': 2.0, 'A': 2.0, '|': 2.0, 'B': 1.0}
class_weight = {int(le.transform([s])[0]): w for s, w in weight_by_symbol.items()}
print('class_weight:', {s: (int(le.transform([s])[0]), w) for s, w in weight_by_symbol.items()})
weight_vec = torch.tensor([class_weight[i] for i in range(NUM_CLASSES)], dtype=torch.float32, device=device)

optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, betas=(0.9, 0.999))
scaler = torch.amp.GradScaler('cuda', enabled=use_amp)

log_dir = os.path.join(args.out_dir, 'tensorboard', 'fit',
                       'torch' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
save_dir = os.path.join(args.out_dir, 'save')
curve_path = os.path.join(args.out_dir, 'loss_curve_torch.png')
os.makedirs(save_dir, exist_ok=True)
writer = SummaryWriter(log_dir)

# 数据搬到 tensor。显存够的话整份常驻 GPU，省掉每个 batch 的 PCIe 拷贝（这个模型很小，拷贝才是瓶颈）
def to_tensor(x, y, on_gpu):
    xt = torch.from_numpy(np.ascontiguousarray(x))
    yt = torch.from_numpy(y).long()
    if on_gpu:
        xt, yt = xt.to(device), yt.to(device)
    return xt, yt

gpu_cache = (device.type == 'cuda') and not args.no_gpu_cache
if gpu_cache:
    need_gb = (X_train.nbytes + X_val.nbytes + X_test.nbytes) / 1024**3
    free_gb = torch.cuda.mem_get_info()[0] / 1024**3
    gpu_cache = need_gb < free_gb * 0.7          # 留出富余给激活值
    print(f'数据集 {need_gb:.2f} GB / 可用显存 {free_gb:.2f} GB -> '
          f'{"常驻显存" if gpu_cache else "留在内存，按 batch 传输"}')

X_train_t, y_train_t = to_tensor(X_train, y_train, gpu_cache)
X_val_t, y_val_t = to_tensor(X_val, y_val, gpu_cache)
X_test_t, y_test_t = to_tensor(X_test, y_test, gpu_cache)
del X_train, X_val, X_test


def run_epoch(Xt, yt, train, desc):
    model.train(train)
    n = len(Xt)
    order = torch.randperm(n, device=Xt.device) if train else torch.arange(n, device=Xt.device)
    tot_loss, tot_correct = 0.0, 0
    preds_all = [] if not train else None
    bar = tqdm(range(0, n, args.batch_size), desc=desc, leave=False)
    with torch.set_grad_enabled(train):
        for i in bar:
            idx = order[i:i + args.batch_size]
            xb, yb = Xt[idx], yt[idx]
            if xb.device != device:
                xb, yb = xb.to(device, non_blocking=True), yb.to(device, non_blocking=True)
            with torch.amp.autocast('cuda', enabled=use_amp):
                logits = model(xb)
                # Keras 的 class_weight 是「逐样本乘权重后对 batch 求平均」，
                # 而 CrossEntropyLoss(weight=...) 默认除以权重之和，两者不等价，所以手动算
                losses = F.cross_entropy(logits.float(), yb, reduction='none')
                loss = (losses * weight_vec[yb]).mean()
            if train:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            bs = yb.size(0)
            tot_loss += loss.item() * bs
            pred = logits.argmax(1)
            tot_correct += (pred == yb).sum().item()
            if preds_all is not None:
                preds_all.append(pred.cpu())
            bar.set_postfix(loss=f'{tot_loss / (i + bs):.4f}', acc=f'{tot_correct / (i + bs):.4f}')
    preds = torch.cat(preds_all).numpy() if preds_all is not None else None
    return tot_loss / n, tot_correct / n, preds


# ===================================================开始训练==================================================
print('begin fit')
history = {'loss': [], 'val_loss': [], 'accuracy': [], 'val_accuracy': []}
best_val = float('inf')
best_path = os.path.join(save_dir, 'best_torch.pt')

for epoch in range(args.epochs):
    t0 = time.time()
    tr_loss, tr_acc, _ = run_epoch(X_train_t, y_train_t, True, f'epoch {epoch + 1}/{args.epochs}')
    va_loss, va_acc, _ = run_epoch(X_val_t, y_val_t, False, 'val')
    history['loss'].append(tr_loss)
    history['val_loss'].append(va_loss)
    history['accuracy'].append(tr_acc)
    history['val_accuracy'].append(va_acc)
    writer.add_scalar('loss/train', tr_loss, epoch)
    writer.add_scalar('loss/val', va_loss, epoch)
    writer.add_scalar('accuracy/train', tr_acc, epoch)
    writer.add_scalar('accuracy/val', va_acc, epoch)

    tag = ''
    if va_loss < best_val:                 # 每个 epoch 存一次最好的，中途崩溃/断电也不会丢掉进度
        best_val = va_loss
        torch.save({'epoch': epoch, 'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(), 'val_loss': va_loss,
                    'classes': list(le.classes_)}, best_path)
        tag = f'  (val_loss improved -> saved)'
    print(f'Epoch {epoch + 1}/{args.epochs}  {time.time() - t0:.1f}s  '
          f'loss {tr_loss:.4f} acc {tr_acc:.4f}  val_loss {va_loss:.4f} val_acc {va_acc:.4f}{tag}')

writer.close()

# 画 loss 曲线
plt.plot(range(1, args.epochs + 1), history['loss'], color='blue', label='train loss')
plt.plot(range(1, args.epochs + 1), history['val_loss'], color='red', label='val loss')
plt.legend()
plt.xlabel('epoch')
plt.ylabel('loss')
plt.savefig(curve_path, dpi=150)          # 存成图片而不是弹窗，避免阻塞后面的评估和模型保存
plt.close()
print('loss 曲线已保存到:', curve_path)

# ===================================================评估==================================================
te_loss, te_acc, te_pred = run_epoch(X_test_t, y_test_t, False, 'test')
print(f'test loss {te_loss:.4f}, test accuracy {te_acc:.4f}')
print('confusion matrix (行=真实, 列=预测, 顺序 %s):' % list(le.classes_))
print(confusion_matrix(y_test, te_pred, labels=list(range(NUM_CLASSES))))

# 保存模型
final_path = os.path.join(save_dir, 'CNN_torch.pt')
torch.save({'model_state_dict': model.state_dict(), 'classes': list(le.classes_),
            'input_shape': (1, 3600)}, final_path)
print('模型已保存到:', final_path)
print('训练过程中 val_loss 最好的一版:', best_path)

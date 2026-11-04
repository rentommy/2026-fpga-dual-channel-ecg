"""
main_torch.py 的改进版（PyTorch / Windows）。相对原版改了五处：

1. 评估前重新加载最优权重 —— 原版直接用最后一轮的过拟合模型测试
2. 测试结果落盘 —— test_result / 混淆矩阵热力图 / 分类别指标，不再只打印在控制台
3. EarlyStopping —— 被监控指标连续 patience 轮不改善就停，省掉过拟合的那几十轮
4. N 的类别权重 0.1 -> 0.4 —— 原来压得太狠，导致 A/|/V 三类误报率极高
5. 选点判据改用验证集 macro-F1（--monitor）—— 加权 val_loss 在 N 权重低时会
   偏向「多猜少数类」，用它选点反而选到整体最差的一轮（w01 那次 acc 掉到 0.855）

所有产物带 --tag 后缀（默认 main1），不会覆盖 main_torch.py 那次的结果，方便对比。
"""
import argparse
import datetime
import os
import time

import matplotlib
matplotlib.use('Agg')                  # 不弹窗，直接存图
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

import torch
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter

from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import confusion_matrix, classification_report, f1_score
from sklearn import preprocessing

# 调用模型架构
from model.SENetLSTM_torch import SENetLSTM


# ===================================================命令行参数==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description='ECG 分类 (SENet + LSTM) PyTorch 改进版')
parser.add_argument('--data-dir', default=os.path.join(BASE_DIR, 'Data'), help='csv 数据目录')
parser.add_argument('--out-dir', default=BASE_DIR, help='日志/模型/曲线的输出根目录')
parser.add_argument('--tag', default='main2', help='产物文件名后缀，换个 tag 就不会覆盖上次结果')
parser.add_argument('--epochs', type=int, default=60)
parser.add_argument('--batch-size', type=int, default=256,
                    help='GPU 上 256 吞吐更高（上次 acc 0.9005 那次就是 256）；'
                         '只有要和 TF 版 main.py 严格对齐时才用 32')
parser.add_argument('--lr', type=float, default=0.001)
parser.add_argument('--patience', type=int, default=10,
                    help='EarlyStopping：被监控指标连续多少轮不改善就停，设 0 关闭')
parser.add_argument('--monitor', default='val_macro_f1', choices=['val_macro_f1', 'val_loss'],
                    help='选最优权重 / EarlyStopping 的判据。val_loss 是加权损失，'
                         'N 权重压低时它会偏向「多猜少数类」，和整体表现脱节（w01 那次就栽在这），'
                         '所以默认改用验证集 macro-F1')
parser.add_argument('--n-weight', type=float, default=0.4,
                    help='N（正常心拍）的类别权重。原版是 0.1，压得太狠导致误报多')
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
X_list = [os.path.join(args.data_dir, f) for f in [
    '0MLIIIecg_data.csv', '1MLIIecg_data.csv', '2ECGecg_data.csv', '3ECGecg_data.csv']]
Y_list = [os.path.join(args.data_dir, f) for f in [
    '0MLIIIsymbols_data.csv', '1MLIIsymbols_data.csv', '2ECGsymbols_data.csv', '3ECGsymbols_data.csv']]

for f in X_list + Y_list:               # 早点报错，别等加载到一半才发现文件不在
    if not os.path.isfile(f):
        raise SystemExit(f'找不到数据文件: {f}\n请用 --data-dir 指定 csv 所在目录')

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

keep = Y != 'Q'                # 删除Q
X = X[keep]
Y = Y[keep]

# 每样本去直流 + 标准化（减均值、除标准差，去掉电极直流偏置）
X -= X.mean(axis=1, keepdims=True)
X /= (X.std(axis=1, keepdims=True) + 1e-8)
X = np.expand_dims(X, axis=1)    # PyTorch 的 Conv1d 是 (N, C, L)

# 把标签编码
AAMI = ['N', 'L', 'R', 'V', 'A', '|', 'B']
NUM_CLASSES = len(AAMI)
le = preprocessing.LabelEncoder()
le = le.fit(AAMI)
Y = le.transform(Y)
CLASS_NAMES = [str(c) for c in le.classes_]     # 转成普通字符串，别留 np.str_（存盘和打印都难看）

sss = StratifiedShuffleSplit(n_splits=1, test_size=0.1, train_size=0.9, random_state=0)
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


# ===================================================训练准备==================================================
# 类别权重：少数类给大权重，缓解数据不平衡
# 注意 LabelEncoder 是按字母序编码的（A=0,B=1,L=2,N=3,R=4,V=5,|=6），不是上面 AAMI 列表的顺序，
# 所以这里按标签名去查编号，不能写死数字，否则权重会加到错误的类别上
# 【改动 4】N 从 0.1 提到 0.4：0.1 时 N 有 970 个被误判成 A/|/V，导致预测为 A 的样本里 69.5% 其实是 N
weight_by_symbol = {'N': args.n_weight, 'L': 1.0, 'R': 1.0, 'V': 2.0, 'A': 2.0, '|': 2.0, 'B': 1.0}
class_weight = {int(le.transform([s])[0]): w for s, w in weight_by_symbol.items()}
print('class_weight:', {s: (int(le.transform([s])[0]), w) for s, w in weight_by_symbol.items()})
weight_vec = torch.tensor([class_weight[i] for i in range(NUM_CLASSES)], dtype=torch.float32, device=device)

optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, betas=(0.9, 0.999))
scaler = torch.amp.GradScaler('cuda', enabled=use_amp)

tag = args.tag
log_dir = os.path.join(args.out_dir, 'tensorboard', 'fit',
                       f'{tag}-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
save_dir = os.path.join(args.out_dir, 'save')
curve_path = os.path.join(args.out_dir, f'loss_curve_{tag}.png')
cm_path = os.path.join(args.out_dir, f'confusion_matrix_{tag}.png')
result_path = os.path.join(args.out_dir, f'test_result_{tag}.txt')
best_path = os.path.join(save_dir, f'best_{tag}.pt')
final_path = os.path.join(save_dir, f'final_{tag}.pt')
os.makedirs(save_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)
writer = SummaryWriter(log_dir)


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
print(f'begin fit  (选点判据: {args.monitor})')
history = {'loss': [], 'val_loss': [], 'accuracy': [], 'val_accuracy': [], 'val_macro_f1': []}
# 【改动 5】判据可选。val_loss 越小越好，macro-F1 越大越好，用 sign 统一成「越大越好」
higher_is_better = args.monitor == 'val_macro_f1'
best_score = -float('inf')
best_epoch = -1
best_stats = {}
no_improve = 0            # 【改动 3】EarlyStopping 的计数器
stopped_early = False

for epoch in range(args.epochs):
    t0 = time.time()
    tr_loss, tr_acc, _ = run_epoch(X_train_t, y_train_t, True, f'epoch {epoch + 1}/{args.epochs}')
    va_loss, va_acc, va_pred = run_epoch(X_val_t, y_val_t, False, 'val')
    # 验证集是按 arange 顺序跑的，va_pred 与 y_val 一一对应
    va_f1 = f1_score(y_val, va_pred, labels=list(range(NUM_CLASSES)), average='macro', zero_division=0)
    history['loss'].append(tr_loss)
    history['val_loss'].append(va_loss)
    history['accuracy'].append(tr_acc)
    history['val_accuracy'].append(va_acc)
    history['val_macro_f1'].append(va_f1)
    writer.add_scalar('loss/train', tr_loss, epoch)
    writer.add_scalar('loss/val', va_loss, epoch)
    writer.add_scalar('accuracy/train', tr_acc, epoch)
    writer.add_scalar('accuracy/val', va_acc, epoch)
    writer.add_scalar('macro_f1/val', va_f1, epoch)

    score = va_f1 if higher_is_better else -va_loss     # 统一成越大越好
    if score > best_score:                 # 每个 epoch 存一次最好的，中途崩溃/断电也不会丢掉进度
        best_score, best_epoch, no_improve = score, epoch, 0
        best_stats = {'val_loss': va_loss, 'val_accuracy': va_acc, 'val_macro_f1': va_f1}
        torch.save({'epoch': epoch, 'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(), 'monitor': args.monitor,
                    'classes': CLASS_NAMES, **best_stats}, best_path)
        note = f'  ({args.monitor} improved -> saved)'
    else:
        no_improve += 1
        note = f'  (no improve {no_improve}/{args.patience})' if args.patience else ''
    print(f'Epoch {epoch + 1}/{args.epochs}  {time.time() - t0:.1f}s  '
          f'loss {tr_loss:.4f} acc {tr_acc:.4f}  val_loss {va_loss:.4f} val_acc {va_acc:.4f} '
          f'val_macroF1 {va_f1:.4f}{note}', flush=True)

    if args.patience and no_improve >= args.patience:
        stopped_early = True
        print(f'\nEarlyStopping: {args.monitor} 已连续 {args.patience} 轮没有改善，'
              f'在第 {epoch + 1} 轮停止（最优是第 {best_epoch + 1} 轮，'
              f'{args.monitor} {best_stats[args.monitor]:.4f}）')
        break

writer.close()
epochs_run = len(history['loss'])
torch.save({'model_state_dict': model.state_dict(), 'classes': CLASS_NAMES,
            'input_shape': (1, 3600)}, final_path)      # 最后一轮，留作对比

# 画 loss 曲线（横轴用实际跑了多少轮，EarlyStopping 提前停时也不会错位）
# 右轴叠加验证集 macro-F1：加权 loss 和 macro-F1 常常不同步，画在一起才看得出选点选在哪
ep = range(1, epochs_run + 1)
fig, ax = plt.subplots()
ax.plot(ep, history['loss'], color='blue', label='train loss')
ax.plot(ep, history['val_loss'], color='red', label='val loss')
ax.set_xlabel('epoch')
ax.set_ylabel('loss')
ax2 = ax.twinx()
ax2.plot(ep, history['val_macro_f1'], color='green', linestyle=':', label='val macro-F1')
ax2.set_ylabel('macro-F1')
if best_epoch >= 0:
    ax.axvline(best_epoch + 1, color='gray', linestyle='--', linewidth=1,
               label=f'best (epoch {best_epoch + 1}, by {args.monitor})')
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc='center right', fontsize=8)
ax.set_title(f'loss curve ({tag})')
fig.tight_layout()
fig.savefig(curve_path, dpi=150)
plt.close(fig)
print('loss 曲线已保存到:', curve_path)


# ===================================================评估==================================================
# 【改动 1】用最优的那版权重去测试，而不是最后一轮的过拟合模型（判据见 --monitor）
ckpt = torch.load(best_path, map_location=device, weights_only=False)
model.load_state_dict(ckpt['model_state_dict'])
print(f"\n已加载最优权重 (判据 {ckpt['monitor']}): epoch {ckpt['epoch'] + 1}, "
      f"val_loss {ckpt['val_loss']:.4f}, val_acc {ckpt['val_accuracy']:.4f}, "
      f"val_macroF1 {ckpt['val_macro_f1']:.4f}")

te_loss, te_acc, te_pred = run_epoch(X_test_t, y_test_t, False, 'test')
cm = confusion_matrix(y_test, te_pred, labels=list(range(NUM_CLASSES)))
te_f1 = f1_score(y_test, te_pred, labels=list(range(NUM_CLASSES)), average='macro', zero_division=0)
report = classification_report(y_test, te_pred, labels=list(range(NUM_CLASSES)),
                               target_names=CLASS_NAMES, digits=4, zero_division=0)

print(f'\ntest loss {te_loss:.4f}, test accuracy {te_acc:.4f}, test macro-F1 {te_f1:.4f}')
print('confusion matrix (行=真实, 列=预测, 顺序 %s):' % CLASS_NAMES)
print(cm)
print('\n' + report)

# 【改动 2】测试结果落盘，不用再手抄控制台
n_idx = CLASS_NAMES.index('N')
lines = [
    f'运行标签: {tag}',
    f'时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
    f'设备: {device}' + (f' ({torch.cuda.get_device_name(0)})' if device.type == 'cuda' else ''),
    '',
    '--- 超参 ---',
    f'epochs: 设定 {args.epochs}, 实际跑了 {epochs_run}' + ('（EarlyStopping 提前停止）' if stopped_early else ''),
    f'batch_size: {args.batch_size}, lr: {args.lr}, patience: {args.patience}, seed: {args.seed}',
    f'选点判据 (monitor): {args.monitor}',
    f'class_weight: ' + str({s: w for s, w in weight_by_symbol.items()}),
    f'可训练参数: {n_params:,}',
    '',
    '--- 训练过程 ---',
    f'最优轮次: epoch {best_epoch + 1}  '
    f'(val_loss {best_stats["val_loss"]:.4f}, val_acc {best_stats["val_accuracy"]:.4f}, '
    f'val_macroF1 {best_stats["val_macro_f1"]:.4f})',
    f'最后一轮: epoch {epochs_run}  '
    f'(val_loss {history["val_loss"][-1]:.4f}, val_acc {history["val_accuracy"][-1]:.4f}, '
    f'val_macroF1 {history["val_macro_f1"][-1]:.4f}, train_loss {history["loss"][-1]:.4f})',
    '',
    f'--- 测试集（使用 {args.monitor} 最优的权重）---',
    f'test accuracy: {te_acc:.4f}',
    f'test macro-F1: {te_f1:.4f}',
    f'test loss:     {te_loss:.4f}   '
    f'(注意：loss 是按上面的 class_weight 加权算的，改了权重就不能跨运行比较，只能比 accuracy / macro-F1)',
    '',
    f'混淆矩阵 (行=真实, 列=预测, 顺序 {CLASS_NAMES}):',
    str(cm),
    '',
    '分类别指标:',
    report,
    'N 类误判流向 (类别权重压低 N 时这里会变多):',
]
for j in np.argsort(-cm[n_idx]):
    if j != n_idx and cm[n_idx, j] > 0:
        lines.append(f'  N -> {CLASS_NAMES[j]:<2} {cm[n_idx, j]:>5} 个')
lines.append(f'  N 合计误判 {cm[n_idx].sum() - cm[n_idx, n_idx]} / {cm[n_idx].sum()}')
lines.append('')
lines.append('各类预测中混入的 N 的比例:')
for j, c in enumerate(CLASS_NAMES):
    if j != n_idx and cm[:, j].sum() > 0:
        lines.append(f'  预测为 {c:<2}: 共 {cm[:, j].sum():>5} 个, 其中 {cm[n_idx, j]:>5} 个其实是 N '
                     f'({cm[n_idx, j] / cm[:, j].sum() * 100:>5.1f}%)')

with open(result_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print('测试结果已保存到:', result_path)

# 混淆矩阵热力图（按行归一化看召回率；标签用 ASCII，避免中文字体缺失变成方块）
row_sum = cm.sum(axis=1, keepdims=True)
cm_norm = np.divide(cm, row_sum, out=np.zeros_like(cm, dtype=float), where=row_sum > 0)
fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(cm_norm, cmap='Blues', vmin=0, vmax=1)
ax.set_xticks(range(NUM_CLASSES), CLASS_NAMES)
ax.set_yticks(range(NUM_CLASSES), CLASS_NAMES)
ax.set_xlabel('predicted')
ax.set_ylabel('true')
ax.set_title(f'confusion matrix ({tag})  acc={te_acc:.4f}')
for i in range(NUM_CLASSES):
    for j in range(NUM_CLASSES):
        ax.text(j, i, f'{cm[i, j]}\n{cm_norm[i, j] * 100:.1f}%', ha='center', va='center',
                fontsize=7, color='white' if cm_norm[i, j] > 0.5 else 'black')
fig.colorbar(im, ax=ax, label='recall (row-normalized)')
fig.tight_layout()
fig.savefig(cm_path, dpi=150)
plt.close(fig)
print('混淆矩阵热力图已保存到:', cm_path)

print('\n最优模型:', best_path)
print('最后一轮模型:', final_path)

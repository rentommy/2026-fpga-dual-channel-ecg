import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
import pandas as pd
import os
import platform
import datetime
import tensorflow as tf
from tqdm import tqdm

from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, losses
from tensorflow.keras.models import Model
from sklearn import preprocessing

#调用模型架构
from model.SENetLSTM import SENet_LSTM
print("load data...")

path = r"D:/桌面/心率作业/项目复现/ECG_ren/Data/"         # 导入csv文件路径
X_list=[
    path + '0MLIIIecg_data.csv',
    path + '1MLIIecg_data.csv',
    path + '2ECGecg_data.csv',
    path + '3ECGecg_data.csv']

Y_list=[
    path + '0MLIIIsymbols_data.csv',
    path + '1MLIIsymbols_data.csv',
    path + '2ECGsymbols_data.csv',
    path + '3ECGsymbols_data.csv']

#合并数据集
print("begin concatenating...")

# 直接按 float32 读取：不要用 dtype="str" 再转，字符串中间数组会占用近 4 倍内存（单个文件就要 6GB+）
X_parts=[]
for i in tqdm(range(0,len(X_list)), desc="处理记录"):
    X_parts.append(np.loadtxt(X_list[i],delimiter=',',skiprows=1).astype('float32'))
X=np.concatenate(X_parts)        # 一次性拼接，避免循环里反复复制
del X_parts

Y_parts=[]
for i in tqdm(range(0,len(Y_list)), desc="处理记录"):
    Y_parts.append(np.loadtxt(Y_list[i],dtype="str",delimiter=',',skiprows=1))
Y=np.concatenate(Y_parts)
del Y_parts

print('X shape:', X.shape)   # 应该是 (总样本数, 3600)
print('Y shape:', Y.shape)

delete_list = []
for i in range(len(Y)):
    if Y[i] == 'Q':            # 删除Q
        delete_list.append(i)
X=np.delete(X,delete_list,0)
Y=np.delete(Y,delete_list,0)

# 每样本去直流 + 标准化（减均值、除标准差，去掉电极直流偏置）
# 原地运算，避免生成两份 1.7GB 的临时副本
X -= X.mean(axis=1, keepdims=True)
X /= (X.std(axis=1, keepdims=True) + 1e-8)
X = np.expand_dims(X, axis=2)    #增加通道维度


# 把标签编码
AAMI = ['N','L','R','V','A','|','B']
le=preprocessing.LabelEncoder()                            #标签字符变编码
le=le.fit(AAMI)
Y=le.transform(Y)

sss = StratifiedShuffleSplit(n_splits=1, test_size=0.1, train_size=0.9,random_state=0)     # 1:9分割测试集和训练集
for train_index, test_index in sss.split(X, Y):
    X_train, X_test = X[train_index], X[test_index]
    y_train, y_test = Y[train_index], Y[test_index]

    y_train=np.eye(7)[y_train]                                                             # 生成独热编码

del X, Y      # 训练集/测试集已复制出来，释放整份数据占用的内存

'''
def get_batch(X,y,batch_size):                                                             # 随机抽取训练样本
    index = np.random.randint(0, len(y), batch_size)
    return X[index, :], y[index]
'''

#===================================================模型训练==================================================
# 定义超参数
num_epochs = 60
batch_size = 32
learning_rate = 0.001
#=======================================一维 CNN模型====================================================
# =======================================直接调用的方式===================================
input_ecg=tf.keras.layers.Input(shape=(3600,1))                  # 创建输入层，设置模型结构
label_ecg=SENet_LSTM(input_ecg)                                  # 调用自定义层
print("begin 1dCNN")
model=Model(input_ecg,label_ecg)                                 # 将input_ecg输入层 和 label_ecg输出层 封装成一个模型对象
print('model summary:',model.summary())


# 设置优化器
optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate,beta_1=0.9,beta_2=0.999,name='Adam')      #实例化优化器，设置优化器参数
loss=tf.keras.losses.categorical_crossentropy                    # 设置分类交叉熵损失函数
metrics=['accuracy']                                             # 存准确率

# 初始化tensorboard
# 注意windows系统和linux系统下文件路径的问题
if platform.system()=='Windows':                                 # 设置日志路径
    base_dir="D:/桌面/心率作业/项目复现/ECG_ren"
elif platform.system()=='Linux':
    base_dir="."
log_dir=base_dir + "/tensorboard/fit/CNN" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
save_dir=base_dir + "/save"
curve_path=base_dir + "/loss_curve.png"

summary_writer=tf.summary.create_file_writer(log_dir)   # 实例化一个记录器
tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir, histogram_freq=1)

# 每个 epoch 结束时保存 val_loss 最好的一版，训练中途崩溃/断电也不会丢掉进度
os.makedirs(save_dir, exist_ok=True)
checkpoint_callback = tf.keras.callbacks.ModelCheckpoint(
    filepath=save_dir + "/best.keras", monitor='val_loss', save_best_only=True, verbose=1)

# 配置训练过程
print('begin compile CNN')
model.compile(optimizer=optimizer,loss=loss,metrics=metrics)

# 训练模型
print("begin fit CNN")
# 类别权重：少数类给大权重，缓解数据不平衡（N 占96% 给小权重）
# 注意 LabelEncoder 是按字母序编码的（A=0,B=1,L=2,N=3,R=4,V=5,|=6），不是上面 AAMI 列表的顺序，
# 所以这里按标签名去查编号，不能写死数字，否则权重会加到错误的类别上
weight_by_symbol = {'N': 0.1, 'L': 1.0, 'R': 1.0, 'V': 2.0, 'A': 2.0, '|': 2.0, 'B': 1.0}
class_weight = {int(le.transform([s])[0]): w for s, w in weight_by_symbol.items()}
print('class_weight:', {s: (int(le.transform([s])[0]), w) for s, w in weight_by_symbol.items()})
savedModule=model.fit(X_train,y_train,epochs=num_epochs,batch_size=batch_size,validation_split=0.2,class_weight=class_weight,callbacks=[tensorboard_callback,checkpoint_callback])
plt.plot(savedModule.epoch,savedModule.history['loss'],color='blue',label='train loss')
plt.plot(savedModule.epoch,savedModule.history['val_loss'],color="red",label='val loss')   # 来自 validation_split，不是 X_test
plt.legend()
plt.xlabel('epoch')
plt.ylabel('loss')
plt.savefig(curve_path, dpi=150)     # 存成图片而不是弹窗，避免阻塞后面的评估和模型保存
plt.close()
print('loss 曲线已保存到:', curve_path)
# 评估训练效果
y_test_onehot = np.eye(7)[y_test]      # 评估用 one-hot（y_test 本身保持整数给混淆矩阵）
print(model.evaluate(X_test, y_test_onehot))
predict=model.predict(X_test)       # 输出的不是一个类别，而是样本属于每一个类别的概率
predict=[np.argmax(predict[i]) for i in range(len(predict))]
print('confusion matrix:',tf.math.confusion_matrix(y_test,predict))
# 保存模型
tf.saved_model.save(model, save_dir + "/CNN")
print('模型已保存到:', save_dir + "/CNN")
print('训练过程中 val_loss 最好的一版:', save_dir + "/best.keras")
# 模型与训练来源

选定experiment_09/runs/six_db_seed0/best.pt，共195608参数。标签顺序严格为A,F,L,N,R,S,V,|。selected/config.json包含8维RR归一化参数。board/runtime/model/weights.npz为同一权重的部署导出。原始best.pt SHA256为18895c73e08c814d772435a5b07562c6e380cd9f593b76b14ecf4bf9ba40f1bc。

输入为[2,205]、256Hz：标准化心拍波形与有效掩码；R峰索引77。8维RR按配置均值/标准差处理并裁剪[-8,8]。波形预处理与显示PL滤波是不同流程，模型使用ARM侧训练匹配预处理，不能把保真显示缓存直接等同于训练输入。

`network.py`包含独立的Residual/Network定义。从根目录先运行`python sim/make_model_vectors.py`，再运行`python model/export_weights.py`，即可从best.pt重新导出部署权重，并在4组公开合成输入上比对PyTorch。首次运行需安装model/requirements.txt。已验证最大logit误差约9.54e-7，证据在report/evidence/synthetic_model_export.json。

training_snapshot保留既有experiment_09及其直接experiment_08代码。它是来源快照，尚有更早实验划分文件、baseline模型与数据库路径依赖。没有把它冒充独立可运行的全量训练包；完整训练复现仍是待完成项。数据库不重新分发，来源包括MIT-BIH、European ST-T、ST Change、Sudden Cardiac Death、INCART、SVDB，需按各数据源原始条款获取。

49/49是无专家标注自采记录的部署数值一致性，不是模型准确率。selected中的验证指标属于原训练实验的评估协议，不能直接推广到本项目实时电极场景。必须以独立、有标签的数据和患者隔离协议验证分类表现。

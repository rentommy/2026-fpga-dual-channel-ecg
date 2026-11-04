# 2026-11-04 完整干净重建与代码交付

在独立空目录从源码重新综合两个HLS核并导出IP，再从空Vivado工程创建PS/PL设计、综合、布局布线、物理优化并生成bit/hwh；未复制旧IP、xpr、bit或hwh。Vivado/Vitis版本2026.1，器件xc7z020clg400-1。

结果：WNS +0.016 ns，WHS +0.002 ns，setup/hold失败端点均0；最终比特流生成DRC为0错误。资源LUT15735、FF20490、BRAM60、DSP57。证据见evidence/full_clean_build，运行用bit/hwh见board/runtime/overlay。该新构建产物尚未重新加载板卡，已有现场结果属于此前部署版本。

交付根目录保留当前运行、模型导出和构建入口。archive/original_code补充项目源代码、历史算法、训练实验和STM32工程，archive/source_map.json记录原路径与哈希；restore_sources.py可恢复原始目录名称。历史代码保留其版本语法，不将历史Python2代码当作当前运行入口执行。

按用户要求不包含模型训练/项目复现/ECG-with-Deep-learning-master。第三方环境残留、虚拟环境、人体原始记录、录屏、训练数据库、旧检查点和生成的HLS/Vivado工程不收入交付，原始文件均保留。所选模型权重及配置保留。完整训练复现、长期稳定性、最新固件断电验收、公开再分发许可等原有待办不因构建通过而视为完成。

# 全部源码归档

original_code保留工作区src、sim、board、old、model、skill、模型训练、stm32文件及海报工具中的源码/工程配置/说明。包含历史算法与训练实验、STM32 Core和Drivers，不只包含当前上板程序。源码目录名规范化为英文小写，中文名称以稳定摘要编码；原路径、原文件哈希、归档哈希及处理说明见source_map.json。

归档用于保存全部开发代码，不替代仓库根目录的现行复现入口。历史脚本可能依赖原目录结构和本地数据库；可用restore_sources.py在新目录恢复原路径。Notebook保留代码、清除输出，诊断脚本中的明文口令已去除。原始人体心电、录屏、数据库、虚拟环境、工具缓存、生成的HLS/Vivado工程及历史重复权重不属于源码，未收入。

若source_map.json中omissions非空，须检查后再称源码归档完整。原始数据与旧Git历史未删除或改写。

归档补充：已按用户要求排除第三方学习复现目录 `模型训练/项目复现/ECG-with-Deep-learning-master`，以及runtime_backup内的第三方Python环境残留；原始目录均未删除。

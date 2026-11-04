# 模板栏目覆盖与文件说明

来源：`D:/Desktop/AMD_poster_template.pptx`。本次生成文字和技术框图，不改写原PPT模板。原模板中的射电望远镜、光通信板和存储服务器属于示例内容，已按本项目的采集、计算与显示模块对应改写。

| 模板中的文字/占位项 | 文案中的对应栏目 |
|---|---|
| Title | 作品标题 / Project Title |
| Team Member Names | 团队与学校 / Team and Institution |
| 校名、校徽 | 学校待填写、真实授权校徽占位；匿名版删除 |
| INTRODUCTION、背景与关键信息摘要 | 项目简介 |
| Typical application case | 典型应用 |
| Key technical issues addressed | 关键技术问题，5项 |
| System Architecture、系统框图 | 系统架构 + 中英文完整框图 |
| High-speed Acquisition Card等模块说明 | 自主采集与隔离、滤波核、FPGA/ARM识别、交互显示，4模块 |
| CREATIVE DESIGN、关键创新点 | 关键创新点，4项 |
| RESULT、测试结果 | 测试结果与验证边界 |
| 性能 | 性能与资源表 |
| 展望 | Future Work |
| 作品实物缩略图 | 真实实物图说明，需补实际照片 |
| On board test by AMD ZYNQ7000、测试平台信息 | Test Platform |

## 文件

- `poster_text_zh.md`、`poster_text_en.md`：完整模块化文案，不是强制把全部长文塞入一页的排版稿。
- 同名`.txt`：便于用记事本打开并复制。
- `system_diagram_zh/en.svg`：完整系统框图，矢量版适合缩放或插入PPT。
- `system_diagram_zh/en.png`：直接插图版本。
- `system_diagram_zh/en.dot`：Graphviz可编辑源文件。
- `dual_path_detail_zh/en.svg/png/dot`：双路径滤波细节图，适合放在关键创新点区域。
- `generate_diagrams.py`：框图生成源文件。

## 核对依据与措辞边界

1. 两条显示路径共享高通和基线估计，滤波核内部单DSP时分复用。没有沿用历史文档中“CPU做不到”“零额外计算延迟”等过强表述。
2. ARM模型预处理从原始采样分支出发，不能把HDMI保真路径直接画成模型输入。层间归一化在ARM，12层卷积在PL。
3. R峰和心率在ARM，不写成PL实现。30/348ms是滤波脉冲峰值偏移，不是端到端时延。
4. 49/49来自两次独立自采记录的部署对照，不是同步双导联采集，也不是临床准确率。
5. 约120ms/拍与约1.51倍来自后续特定测量，未写成最新显示版本的全覆盖性能结论。
6. 学校名称、校徽、真实照片尚无可确认材料，因此保留明确占位，未虚构。

主要依据：`src/hls/ecg_filter.cpp`、`src/hls/ecg_filter_top.cpp`、`board/dual_view/ecg_model.py`、`stream_inference.py`、`run_inference.py`、`scope_runtime.py`，以及`report/model_deployment_2026-11-04.md`、`monitoring_2026-11-04.md`、`dual_view_2026-11-04.md`、`dual_view_acquisition_followup_2026-11-04.md`和最终时序/资源报告。

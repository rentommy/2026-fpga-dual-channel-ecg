# 复现范围与步骤

1. 主机安装Python和requirements.txt，按根README运行合成向量及主机检查。
2. g++运行滤波核和顶层C测试。精确位宽仿真使用 `vitis-run --mode hls --tcl sim/run_csim_2026.tcl`。
3. 在Vivado/Vitis2026.1命令环境，运行build/build_all.ps1。脚本不会打开工作站旧xpr，而由create_overlay/create_scope和build_system依次创建PS/PL、视频和卷积。
4. build/prepare_vendor.py将配套依赖快照解压到Git忽略目录。HLS导出到hls_ecg2与hls_conv，均不提交生成工程。
5. 构建输出board/runtime/overlay/ecg_inference.bit和同名hwh。先检查skill/report_gate.py及DRC/CDC，不能只看bit文件存在。
6. 将仓库复制到PYNQ，停止旧显示服务，使用board/runtime/install.py安装真实ADC模式，再启动服务。日志通过journalctl查看，/run/ecg-scope/status.json记录采样计数/帧率/丢帧，inference_status.json记录质量与推理状态。
7. 无ADC时不要把合成信号标成当前人体数据。公开候选不带人体回放文件，`--source replay`需自行提供明确来源的文件。公开数值验证使用 `python sim/make_model_vectors.py` 生成的synthetic_inputs.npz，在板端停止显示服务后运行board/runtime/verify_synthetic.py，完成后恢复服务。

2026-11-04已从独立空目录完成两个HLS核综合/IP导出与完整Vivado实现，bit/hwh及新报告已收入交付。时序检查通过，新bit尚未重新上板。详见report/full_clean_build_2026-11-04.md。

训练快照存在旧实验目录依赖，当前仅保证已选定权重的导出/推理范围。尚未建立独立可运行的六数据库全量训练入口，见model/README.md。

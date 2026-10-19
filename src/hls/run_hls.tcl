# run_hls.tcl —— Vitis HLS 批处理综合脚本
#
# 用法（在任意目录）：
#   vitis_hls -f src/hls/run_hls.tcl                 只做 C 仿真 + 综合（最快，几分钟）
#   vitis_hls -f src/hls/run_hls.tcl -tclargs export 再导出 IP
#   vitis_hls -f src/hls/run_hls.tcl -tclargs cosim  再做 C/RTL 协同仿真（慢）
#   vitis_hls -f src/hls/run_hls.tcl -tclargs all    全做
#
# 产物在 build/ecg_filter_hls/solution1/ 下：
#   syn/report/ecg_filter_top_csynth.rpt   资源与时序
#   impl/ip/                                导出的 IP（带 export）
# 跑完用 python sim/collect_hls_report.py 把关键数字提成表格。
#
# 关于 cosim 慢：每采样点约 344 次串行乘法，RTL 仿真 2000 点约 70 万周期。
# 带 cosim 时 N_SIM 会被设成 2000；全长黄金比对由 g++ 侧的
# tb_ecg_filter.cpp 负责（秒级跑完），两边分工见 INTERFACE.md。

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set ROOT [file normalize "$SCRIPT_DIR/../.."]
set HLS  "$ROOT/src/hls"

set DO_COSIM  0
set DO_EXPORT 0
foreach a $argv {
    switch -- $a {
        cosim   { set DO_COSIM 1 }
        export  { set DO_EXPORT 1 }
        all     { set DO_COSIM 1; set DO_EXPORT 1 }
        default { puts "未知参数: $a（可用 cosim / export / all）"; exit 1 }
    }
}

puts "工程根目录 : $ROOT"
puts "cosim      : $DO_COSIM"
puts "export     : $DO_EXPORT"

open_project -reset "$ROOT/build/ecg_filter_hls"
set_top ecg_filter_top

set CF "-I$HLS -std=c++11"
add_files "$HLS/ecg_filter.cpp"     -cflags $CF
add_files "$HLS/ecg_filter_top.cpp" -cflags $CF

# 带 cosim 时缩短仿真长度，否则 RTL 仿真要跑几个小时
if {$DO_COSIM} {
    add_files -tb "$HLS/tb_ecg_filter_top.cpp" -cflags "$CF -DN_SIM=2000"
} else {
    add_files -tb "$HLS/tb_ecg_filter_top.cpp" -cflags $CF
}

# -flow_target 是 2020.2 以后才有的，老版本会报错，退回不带参数的写法
if {[catch {open_solution -reset "solution1" -flow_target vivado}]} {
    puts "（本版本不支持 -flow_target，使用默认流程）"
    open_solution -reset "solution1"
}

# PYNQ-Z2 = XC7Z020-1CLG400C，PS 默认给 100 MHz
set_part {xc7z020clg400-1}
create_clock -period 10 -name default

puts "\n========== C 仿真 =========="
csim_design

puts "\n========== 综合 =========="
csynth_design

if {$DO_COSIM} {
    puts "\n========== C/RTL 协同仿真 =========="
    cosim_design -trace_level none -rtl verilog
}

if {$DO_EXPORT} {
    puts "\n========== 导出 IP =========="
    export_design -format ip_catalog -rtl verilog \
        -display_name "ECG Multi-Channel Dual-Latency Filter" \
        -description "8-channel bioelectric filter with per-channel configurable latency" \
        -vendor "nuaa" -library "ecg" -version "1.0"
}

puts "\n完成。报告在 $ROOT/build/ecg_filter_hls/solution1/syn/report/"
puts "提取关键数字： python sim/collect_hls_report.py"
exit

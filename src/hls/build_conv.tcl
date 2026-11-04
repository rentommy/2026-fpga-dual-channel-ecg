set root [file normalize [file join [file dirname [info script]] ../..]]
cd $root
open_component -reset hls_conv
set_top ecg_conv
add_files src/hls/ecg_conv.cpp
set_part xc7z020clg400-1
create_clock -period 10 -name default
config_compile -pipeline_loops 0
csynth_design
export_design -format ip_catalog -rtl verilog -display_name "ECG FP32 Conv1d" -vendor nuaa -library ecg -version 1.0
exit

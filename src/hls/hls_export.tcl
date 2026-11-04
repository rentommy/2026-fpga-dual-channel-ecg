# Vitis 2026.1 entry. Locate the project independently of the launch directory.
set ecg_root [file normalize [file join [file dirname [info script]] ../..]]
cd $ecg_root
open_component -reset hls_ecg2
set_top ecg_filter_top
add_files src/hls/ecg_filter.cpp
add_files src/hls/ecg_filter_top.cpp
set_part {xc7z020clg400-1}
create_clock -period 10 -name default
config_compile -pipeline_loops 0
set_directive_allocation -limit 1 -type function ecg_filter_top ecg_filter_sample
set_directive_allocation -limit 1 -type operation ecg_filter_sample mul
csynth_design
export_design -format ip_catalog -rtl verilog -display_name "ECG Multi-Channel Dual-Latency Filter" -vendor nuaa -library ecg -version 1.0
exit

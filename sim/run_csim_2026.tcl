# Vitis 2026.1 batch entry: vitis-run --mode hls --tcl sim/run_csim_2026.tcl
# Keep the component's parent equal to the working directory. This avoids the
# source-path resolution failure seen with the old nested open_project flow.
set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set ecg_work [file join $ecg_root build hls_csim]
file mkdir $ecg_work
cd $ecg_work
open_component -reset ecg_csim
set_top ecg_filter_top
add_files ../../src/hls/ecg_filter.cpp
add_files ../../src/hls/ecg_filter_top.cpp
add_files -tb ../../src/hls/tb_ecg_filter_top.cpp
set_part {xc7z020clg400-1}
create_clock -period 10 -name default
csim_design
exit

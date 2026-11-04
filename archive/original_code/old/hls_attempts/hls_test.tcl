open_project -reset D:/ecg_fpga/build/hls_test
set_top ecg_filter_top
add_files D:/ecg_fpga/src/hls/ecg_filter.cpp
add_files D:/ecg_fpga/src/hls/ecg_filter_top.cpp
add_files -tb D:/ecg_fpga/src/hls/tb_ecg_filter_top.cpp
open_solution -reset solution1
set_part {xc7z020clg400-1}
create_clock -period 10 -name default
csim_design
exit

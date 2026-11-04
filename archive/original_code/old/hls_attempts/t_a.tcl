open_project -reset build/hls_a
set_top ecg_filter_top
add_files src/hls/ecg_filter.cpp
add_files src/hls/ecg_filter_top.cpp
open_solution -reset solution1
set_part {xc7z020clg400-1}
create_clock -period 10 -name default
csynth_design
exit

open_component -reset hls_ecg
set_top ecg_filter_top
add_files src/hls/ecg_filter.cpp
add_files src/hls/ecg_filter_top.cpp
set_part {xc7z020clg400-1}
create_clock -period 10 -name default
csynth_design
exit

set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $ecg_root board board_files]]
open_project [file join $ecg_root build vivado ecg_scope ecg_overlay.xpr]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
open_run impl_1
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
report_timing_summary -report_unconstrained -file [file join $ecg_root build scope_postroute_timing.rpt]
set ecg_p [get_timing_paths -delay_type max -max_paths 1]
puts "SCOPE_POSTROUTE_WNS: [get_property SLACK $ecg_p]"
if {[get_property SLACK $ecg_p]<0} {error "Post-route optimization did not close setup timing"}
set ecg_rd [get_property DIRECTORY [get_runs impl_1]]
file mkdir [file join $ecg_root build scope_failed_timing]
file copy -force [file join $ecg_rd ecg_system_wrapper_routed.dcp] [file join $ecg_root build scope_failed_timing ecg_system_wrapper_routed.dcp]
write_checkpoint -force [file join $ecg_rd ecg_system_wrapper_routed.dcp]
write_bitstream -force [file join $ecg_rd ecg_system_wrapper.bit]
set ecg_scope_design_open 1
source [file join $ecg_root board export_scope.tcl]
close_project
exit

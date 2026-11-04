set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $ecg_root board board_files]]
open_project [file join $ecg_root build vivado ecg_scope ecg_overlay.xpr]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
open_bd_design [get_files */ecg_system.bd]
set_property CONFIG.PRIM_SOURCE {No_buffer} [get_bd_cells video_clocks]
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $ecg_root board scope ecg_scope_generated.tcl]
generate_target all [get_files */ecg_system.bd]
update_compile_order -fileset sources_1
reset_run synth_1
reset_run ecg_system_video_clocks_0_synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
source [file join $ecg_root board export_scope.tcl]
close_project
exit

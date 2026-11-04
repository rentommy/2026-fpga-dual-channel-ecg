set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $ecg_root board board_files]]
open_project [file join $ecg_root build vivado ecg_scope ecg_overlay.xpr]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
open_bd_design [get_files */ecg_system.bd]
write_bd_tcl -force [file join $ecg_root board scope ecg_scope_generated.tcl]
close_project
exit

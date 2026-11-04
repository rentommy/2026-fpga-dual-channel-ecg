set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $ecg_root board board_files]]
open_project [file join $ecg_root build vivado ecg_scope ecg_overlay.xpr]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
foreach ecg_header {ecg_chinese_font.vh ecg_chinese_labels.vh} {
    set ecg_header_path [file join $ecg_root src rtl $ecg_header]
    if {![llength [get_files -quiet $ecg_header_path]]} {add_files -norecurse $ecg_header_path}
}
update_compile_order -fileset sources_1
open_bd_design [get_files */ecg_system.bd]
if {[catch {update_module_reference ecg_system_ecg_io_0} ecg_refresh_error ecg_refresh_options]} {
    puts "MODULE_REFRESH_ERROR: $ecg_refresh_error"
    puts [dict get $ecg_refresh_options -errorinfo]
    error "Could not refresh scope module reference"
}
validate_bd_design
save_bd_design
generate_target all [get_files */ecg_system.bd]
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
source [file join $ecg_root board export_scope.tcl]
close_project
exit

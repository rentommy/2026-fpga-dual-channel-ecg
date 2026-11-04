set root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $root board board_files]]
open_project [file join $root build vivado ecg_monitor ecg_overlay.xpr]
save_project_as ecg_overlay [file join $root build vivado ecg_dual_view] -force
open_bd_design [get_files */ecg_system.bd]
file mkdir [file join $root board dual_view rtl]
set fh [open [file join $root src rtl ecg_io_top.sv] r]
set source_text [read $fh]
close $fh
set dual_source [file join $root board dual_view rtl ecg_io_dual_top.sv]
set fh [open $dual_source w]
puts $fh [string map {"module ecg_io_top" "module ecg_io_dual_top"} $source_text]
close $fh
add_files -norecurse $dual_source
update_compile_order -fileset sources_1
# Recreate the module reference so the BD imports the newly added HDL port.
set saved_pins [list]
foreach pin [get_bd_pins ecg_io/*] {
 set nets [get_bd_nets -quiet -of_objects $pin]
 if {[llength $nets]} {lappend saved_pins [list [file tail $pin] [get_property NAME [lindex $nets 0]]]}
}
set axi_net [get_property NAME [get_bd_intf_nets -of_objects [get_bd_intf_pins ecg_io/s_axi]]]
delete_bd_objs [get_bd_cells ecg_io]
create_bd_cell -type module -reference ecg_io_dual_top ecg_io_dual
foreach pair $saved_pins {lassign $pair name net; connect_bd_net -net $net [get_bd_pins ecg_io_dual/$name]}
connect_bd_intf_net [get_bd_intf_pins ctrl_connect/M01_AXI] [get_bd_intf_pins ecg_io_dual/s_axi]
assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *ecg_io*}]
set_property offset 0x40010000 $seg
set_property range 64K $seg
if {![llength [get_bd_ports -quiet sw0]]} {create_bd_port -dir I sw0}
connect_bd_net [get_bd_ports sw0] [get_bd_pins ecg_io_dual/sw0]
validate_bd_design
save_bd_design
generate_target all [get_files */ecg_system.bd]
make_wrapper -files [get_files */ecg_system.bd] -top -force
add_files -fileset constrs_1 [file join $root board dual_view.xdc]
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
open_run impl_1
set out [file join $root board dual_view overlay]
file mkdir $out
for {set attempt 0} {$attempt<4 && [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0} {incr attempt} {
 phys_opt_design -directive AggressiveExplore
 route_design -directive Explore
}
report_timing_summary -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
report_drc -file [file join $out drc.rpt]
report_cdc -file [file join $out cdc.rpt]
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0 || [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]<0} {error "Dual view timing failed"}
write_bitstream -force [file join $out ecg_inference.bit]
file copy -force [lindex [glob [file join [get_property DIRECTORY [current_project]] ecg_overlay.gen sources_1 bd ecg_system hw_handoff *.hwh]] 0] [file join $out ecg_inference.hwh]
puts "ECG_DUAL_VIEW_READY"
close_project
exit

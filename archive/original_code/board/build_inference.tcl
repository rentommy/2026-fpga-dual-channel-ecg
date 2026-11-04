set root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $root board board_files]]
open_project [file join $root build vivado ecg_scope ecg_overlay.xpr]
save_project_as ecg_overlay [file join $root build vivado ecg_inference] -force
set_property ip_repo_paths [list [file join $root hls_ecg2 hls impl ip] [file join $root hls_conv hls impl ip] [file join $root board vendor digilent]] [current_project]
update_ip_catalog
foreach name {ecg_font.vh ecg_chinese_font.vh ecg_chinese_labels.vh} {
 set path [file join $root src rtl $name]
 if {![llength [get_files -quiet $path]]} {add_files -norecurse $path}
}
open_bd_design [get_files */ecg_system.bd]
update_module_reference ecg_system_ecg_io_0
set_property -dict [list CONFIG.PCW_USE_S_AXI_HP2 {1} CONFIG.PCW_USE_S_AXI_HP3 {1}] [get_bd_cells ps7]
set_property CONFIG.NUM_MI 3 [get_bd_cells ctrl_connect]
create_bd_cell -type ip -vlnv nuaa:ecg:ecg_conv:1.0 ecg_conv_0
connect_bd_intf_net [get_bd_intf_pins ctrl_connect/M02_AXI] [get_bd_intf_pins ecg_conv_0/s_axi_ctrl]
foreach {name master slave} {conv_read gmem0 HP2 conv_write gmem1 HP3} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 $name
 set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] [get_bd_cells $name]
 connect_bd_intf_net [get_bd_intf_pins ecg_conv_0/m_axi_$master] [get_bd_intf_pins $name/S00_AXI]
 connect_bd_intf_net [get_bd_intf_pins $name/M00_AXI] [get_bd_intf_pins ps7/S_AXI_$slave]
 connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins $name/aclk] [get_bd_pins ps7/S_AXI_${slave}_ACLK]
 connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] [get_bd_pins $name/aresetn]
}
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ecg_conv_0/ap_clk]
connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] [get_bd_pins ecg_conv_0/ap_rst_n]
assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *ecg_conv_0*}]
set_property offset 0x40020000 $seg
set_property range 64K $seg
validate_bd_design
save_bd_design
generate_target all [get_files */ecg_system.bd]
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
open_run impl_1
for {set attempt 0} {$attempt<4 && [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0} {incr attempt} {
 if {$attempt==0} {phys_opt_design -directive AggressiveExplore} else {phys_opt_design -directive Explore}
 route_design -directive Explore
}
file mkdir [file join $root board inference overlay]
set out [file join $root board inference overlay]
report_timing_summary -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
report_drc -file [file join $out drc.rpt]
report_cdc -file [file join $out cdc.rpt]
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0 || [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]<0} {error "Inference timing failed"}
write_bitstream -force [file join $out ecg_inference.bit]
file copy -force [lindex [glob [file join [get_property DIRECTORY [current_project]] ecg_overlay.gen sources_1 bd ecg_system hw_handoff *.hwh]] 0] [file join $out ecg_inference.hwh]
puts "ECG_INFERENCE_BITSTREAM_READY"
close_project
exit

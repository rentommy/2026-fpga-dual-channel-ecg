# Run inside Vivado 2026.1: source D:/ecg_fpga/board/create_overlay.tcl
# This creates the DDR-backed file-replay overlay, without programming a board.
set ecg_root [file normalize [file join [file dirname [info script]] ..]]
if {![info exists ecg_project_dir]} {
    set ecg_project_dir [file join $ecg_root build vivado ecg_overlay]
}
set ecg_ip_dir [file join $ecg_root hls_ecg2 hls impl ip]
if {[file exists [file join $ecg_project_dir ecg_overlay.xpr]]} {
    error "Project already exists: $ecg_project_dir. Open it instead of overwriting it."
}
if {![file exists [file join $ecg_ip_dir component.xml]]} {
    error "Export the HLS IP first: $ecg_ip_dir/component.xml is missing."
}
set_param board.repoPaths [list [file join $ecg_root board board_files]]
set ecg_board_part [get_board_parts -quiet tul.com.tw:pynq-z2:part0:1.0]
if {[llength $ecg_board_part] != 1} { error "PYNQ-Z2 vendor board files were not discovered." }
create_project ecg_overlay $ecg_project_dir -part xc7z020clg400-1
set_property board_part $ecg_board_part [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list $ecg_ip_dir] [current_project]
update_ip_catalog
create_bd_design ecg_system
set ecg_ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ecg_ps
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_USE_S_AXI_HP1 {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ecg_ps
set ecg_filter [create_bd_cell -type ip -vlnv nuaa:ecg:ecg_filter_top:1.0 ecg_filter_0]
foreach ecg_name {ctrl_connect read_connect write_connect} {
    set ecg_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 $ecg_name]
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] $ecg_sc
}
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_100m
# External polarity is inferred from FCLK_RESET0_N (read-only in this Vivado).
# Auxiliary polarity defaults to active-low, so explicitly make tied-low inactive.
set_property CONFIG.C_AUX_RESET_HIGH {1} [get_bd_cells reset_100m]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_one
set_property CONFIG.CONST_VAL {1} [get_bd_cells const_one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_zero
set_property CONFIG.CONST_VAL {0} [get_bd_cells const_zero]
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins ctrl_connect/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ctrl_connect/M00_AXI] [get_bd_intf_pins ecg_filter_0/s_axi_ctrl]
connect_bd_intf_net [get_bd_intf_pins ecg_filter_0/m_axi_gmem0] [get_bd_intf_pins read_connect/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins read_connect/M00_AXI] [get_bd_intf_pins ps7/S_AXI_HP0]
connect_bd_intf_net [get_bd_intf_pins ecg_filter_0/m_axi_gmem1] [get_bd_intf_pins write_connect/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins write_connect/M00_AXI] [get_bd_intf_pins ps7/S_AXI_HP1]
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] \
    [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins ps7/S_AXI_HP0_ACLK] \
    [get_bd_pins ps7/S_AXI_HP1_ACLK] [get_bd_pins ecg_filter_0/ap_clk] \
    [get_bd_pins ctrl_connect/aclk] [get_bd_pins read_connect/aclk] \
    [get_bd_pins write_connect/aclk] [get_bd_pins reset_100m/slowest_sync_clk]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins reset_100m/ext_reset_in]
connect_bd_net [get_bd_pins const_one/dout] [get_bd_pins reset_100m/dcm_locked]
connect_bd_net [get_bd_pins const_zero/dout] [get_bd_pins reset_100m/aux_reset_in] [get_bd_pins reset_100m/mb_debug_sys_rst]
connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] \
    [get_bd_pins ecg_filter_0/ap_rst_n] [get_bd_pins ctrl_connect/aresetn] \
    [get_bd_pins read_connect/aresetn] [get_bd_pins write_connect/aresetn]
assign_bd_address
set ecg_ctrl_segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *ecg_filter_0*}]
if {[llength $ecg_ctrl_segments] != 1} { error "Could not uniquely identify the filter control address segment." }
set_property offset 0x40000000 $ecg_ctrl_segments
set_property range 64K $ecg_ctrl_segments
validate_bd_design
if {[get_property CONFIG.C_AUX_RESET_HIGH [get_bd_cells reset_100m]] != 1} {
    error "aux_reset_in is tied low and must be active-high; otherwise AXI remains in reset."
}
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells reset_100m]] != 0} {
    error "FCLK_RESET0_N requires an active-low external reset input."
}
save_bd_design
set ecg_bd_file [get_files */ecg_system.bd]
generate_target all $ecg_bd_file
set ecg_wrappers [make_wrapper -files $ecg_bd_file -top]
add_files -norecurse $ecg_wrappers
set_property top ecg_system_wrapper [current_fileset]
update_compile_order -fileset sources_1
file mkdir [file join $ecg_root board overlay]
write_bd_tcl -force [file join $ecg_root board overlay ecg_system_generated.tcl]
puts "ECG_DESIGN_READY: $ecg_project_dir/ecg_overlay.xpr"
puts "Next: source [file join $ecg_root board build_overlay.tcl]"

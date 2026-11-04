# Fresh combined ADC + HLS filter + standalone HDMI waveform overlay.
set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $ecg_root board board_files]]
set ecg_project_dir [file join $ecg_root build vivado ecg_scope]
if {[file exists [file join $ecg_project_dir ecg_overlay.xpr]]} {
 open_project [file join $ecg_project_dir ecg_overlay.xpr]
 open_bd_design [get_files */ecg_system.bd]
 if {[llength [get_bd_cells -quiet ecg_io]]} {error "Scope design already exists; open/rebuild that project instead."}
} else {source [file join $ecg_root board create_overlay.tcl]}
close_bd_design [current_bd_design]
set_property ip_repo_paths [list [file join $ecg_root hls_ecg2 hls impl ip] [file join $ecg_root board vendor digilent]] [current_project]
update_ip_catalog
add_files -norecurse [glob [file join $ecg_root src rtl *.sv]]
add_files -norecurse [glob [file join $ecg_root src rtl *.vh]]
set_property include_dirs [list [file join $ecg_root src rtl]] [current_fileset]
update_compile_order -fileset sources_1
open_bd_design [get_files */ecg_system.bd]
create_bd_cell -type module -reference ecg_io_top ecg_io
set_property CONFIG.NUM_MI {2} [get_bd_cells ctrl_connect]
set ecg_axi [get_bd_intf_pins -of_objects [get_bd_cells ecg_io] -filter {VLNV =~ *aximm_rtl*}]
if {[llength $ecg_axi]!=1} {error "Could not infer ecg_io AXI interface: $ecg_axi"}
connect_bd_intf_net [get_bd_intf_pins ctrl_connect/M01_AXI] $ecg_axi
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 video_clocks
set_property -dict [list CONFIG.PRIM_IN_FREQ {100.000} CONFIG.PRIM_SOURCE {No_buffer} CONFIG.NUM_OUT_CLKS {2} \
 CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {25.200} CONFIG.CLKOUT2_USED {true} \
 CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {126.000} CONFIG.RESET_TYPE {ACTIVE_LOW} \
 CONFIG.USE_RESET {true} CONFIG.USE_LOCKED {true}] [get_bd_cells video_clocks]
create_bd_cell -type ip -vlnv digilentinc.com:ip:rgb2dvi:1.4 hdmi_encoder
set_property -dict [list CONFIG.kGenerateSerialClk {false} CONFIG.kRstActiveHigh {false}] [get_bd_cells hdmi_encoder]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_video
set_property CONFIG.C_AUX_RESET_HIGH {1} [get_bd_cells reset_video]
set_property CONFIG.C_EXT_RESET_HIGH {0} [get_bd_cells reset_video]
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ecg_io/s_axi_aclk] [get_bd_pins video_clocks/clk_in1]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins video_clocks/resetn] [get_bd_pins reset_video/ext_reset_in]
# Clock wizard resets directly from PS; resetting it with reset_100m would deadlock lock detection.
disconnect_bd_net [get_bd_nets -of_objects [get_bd_pins reset_100m/dcm_locked]] [get_bd_pins reset_100m/dcm_locked]
connect_bd_net [get_bd_pins video_clocks/locked] [get_bd_pins reset_100m/dcm_locked] [get_bd_pins reset_video/dcm_locked]
connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] [get_bd_pins ecg_io/s_axi_aresetn]
connect_bd_net [get_bd_pins const_zero/dout] [get_bd_pins reset_video/aux_reset_in] [get_bd_pins reset_video/mb_debug_sys_rst]
connect_bd_net [get_bd_pins video_clocks/clk_out1] [get_bd_pins reset_video/slowest_sync_clk] \
 [get_bd_pins ecg_io/pixel_clk] [get_bd_pins hdmi_encoder/PixelClk]
connect_bd_net [get_bd_pins video_clocks/clk_out2] [get_bd_pins hdmi_encoder/SerialClk]
connect_bd_net [get_bd_pins reset_video/peripheral_aresetn] [get_bd_pins ecg_io/pixel_resetn] [get_bd_pins hdmi_encoder/aRst_n]
connect_bd_net [get_bd_pins ecg_io/video_rgb] [get_bd_pins hdmi_encoder/vid_pData]
connect_bd_net [get_bd_pins ecg_io/video_de] [get_bd_pins hdmi_encoder/vid_pVDE]
connect_bd_net [get_bd_pins ecg_io/video_hsync] [get_bd_pins hdmi_encoder/vid_pHSync]
connect_bd_net [get_bd_pins ecg_io/video_vsync] [get_bd_pins hdmi_encoder/vid_pVSync]
proc scope_port {name dir pin {left -1}} {
 if {$left>=0} {set p [create_bd_port -dir $dir -from $left -to 0 $name]} else {set p [create_bd_port -dir $dir $name]}
 connect_bd_net $p [get_bd_pins $pin]
}
foreach p {ads_cs_n ads_sclk ads_din ads_start ads_pwdn_reset_n} {scope_port $p O ecg_io/$p}
foreach p {ads_dout ads_drdy_n hdmi_hpd} {scope_port $p I ecg_io/$p}
scope_port buttons I ecg_io/buttons 3
scope_port sw0 I ecg_io/sw0
scope_port hdmi_clk_p O hdmi_encoder/TMDS_Clk_p
scope_port hdmi_clk_n O hdmi_encoder/TMDS_Clk_n
scope_port hdmi_data_p O hdmi_encoder/TMDS_Data_p 2
scope_port hdmi_data_n O hdmi_encoder/TMDS_Data_n 2
assign_bd_address
set ecg_io_seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *ecg_io*}]
if {[llength $ecg_io_seg]!=1} {error "Missing ecg_io control address segment"}
set_property offset 0x40010000 $ecg_io_seg
set_property range 64K $ecg_io_seg
validate_bd_design
save_bd_design
generate_target all [get_files */ecg_system.bd]
set_property top ecg_system_wrapper [current_fileset]
add_files -fileset constrs_1 [file join $ecg_root board ads1292_pmoda.xdc]
add_files -fileset constrs_1 [file join $ecg_root board scope_hdmi.xdc]
update_compile_order -fileset sources_1
file mkdir [file join $ecg_root board scope]
write_bd_tcl -force [file join $ecg_root board scope ecg_scope_generated.tcl]
puts "ECG_SCOPE_READY"

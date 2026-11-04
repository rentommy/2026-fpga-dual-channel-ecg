open_project D:/ecg_fpga/build/vivado/ecg_dual_view/ecg_overlay.xpr
open_bd_design [get_files */ecg_system.bd]
puts [help update_module_reference]
puts "REFRESH [info commands *module*ref*]"
puts "MODULE_FILES [get_files *ecg_io_top*]"
puts "MODULE_IPS [get_ips *ecg_io*]"
puts "PINS [get_bd_pins ecg_io/*]"
exit

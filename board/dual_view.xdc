# PYNQ-Z2 board_files part0_pins.xml: SW0=M20.
set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33} [get_ports sw0]
set_false_path -from [get_ports sw0] -to [get_pins -hier -filter {NAME =~ */sw_meta_reg/D}]

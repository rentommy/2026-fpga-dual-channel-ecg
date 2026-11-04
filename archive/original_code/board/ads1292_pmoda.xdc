# PYNQ-Z2 Pmod A. HOST SIDE of isolation only. Ports required in the SPI top.
# Flat XDC commands: Vivado XDC does not support arbitrary Tcl loops.
set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {ads_cs_n}]
set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports {ads_din}]
set_property -dict {PACKAGE_PIN Y16 IOSTANDARD LVCMOS33} [get_ports {ads_dout}]
set_property -dict {PACKAGE_PIN Y17 IOSTANDARD LVCMOS33} [get_ports {ads_sclk}]
set_property -dict {PACKAGE_PIN U18 IOSTANDARD LVCMOS33} [get_ports {ads_drdy_n}]
set_property -dict {PACKAGE_PIN U19 IOSTANDARD LVCMOS33} [get_ports {ads_start}]
set_property -dict {PACKAGE_PIN W18 IOSTANDARD LVCMOS33} [get_ports {ads_pwdn_reset_n}]
set_property SLEW SLOW [get_ports {ads_cs_n ads_din ads_sclk ads_start ads_pwdn_reset_n}]
set_property DRIVE 8 [get_ports {ads_cs_n ads_din ads_sclk ads_start ads_pwdn_reset_n}]

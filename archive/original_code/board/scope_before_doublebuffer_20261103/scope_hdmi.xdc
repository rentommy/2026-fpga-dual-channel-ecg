# TUL PYNQ-Z2 HDMI OUT and buttons.
set_property -dict {PACKAGE_PIN L16 IOSTANDARD TMDS_33} [get_ports {hdmi_clk_p}]
set_property -dict {PACKAGE_PIN L17 IOSTANDARD TMDS_33} [get_ports {hdmi_clk_n}]
set_property -dict {PACKAGE_PIN K17 IOSTANDARD TMDS_33} [get_ports {hdmi_data_p[0]}]
set_property -dict {PACKAGE_PIN K18 IOSTANDARD TMDS_33} [get_ports {hdmi_data_n[0]}]
set_property -dict {PACKAGE_PIN K19 IOSTANDARD TMDS_33} [get_ports {hdmi_data_p[1]}]
set_property -dict {PACKAGE_PIN J19 IOSTANDARD TMDS_33} [get_ports {hdmi_data_n[1]}]
set_property -dict {PACKAGE_PIN J18 IOSTANDARD TMDS_33} [get_ports {hdmi_data_p[2]}]
set_property -dict {PACKAGE_PIN H18 IOSTANDARD TMDS_33} [get_ports {hdmi_data_n[2]}]
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33} [get_ports {buttons[0]}]
set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33} [get_ports {buttons[1]}]
set_property -dict {PACKAGE_PIN L20 IOSTANDARD LVCMOS33} [get_ports {buttons[2]}]
set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS33} [get_ports {buttons[3]}]
set_property -dict {PACKAGE_PIN R19 IOSTANDARD LVCMOS33} [get_ports {hdmi_hpd}]
# Asynchronous board inputs terminate only at the first synchronizer stage.
# Internal synchronizer paths and all pixel/serial timing remain constrained.
set_false_path -from [get_ports ads_drdy_n] -to [get_pins -hier -filter {NAME =~ */drdy_meta_reg/D}]
set_false_path -from [get_ports ads_dout] -to [get_pins -hier -filter {NAME =~ */miso_meta_reg/D}]
set_false_path -from [get_ports buttons*] -to [get_pins -hier -filter {NAME =~ */btn_meta_reg*/D}]
set_false_path -from [get_ports hdmi_hpd] -to [get_pins -hier -filter {NAME =~ */hpd_meta_reg/D}]
set_false_path -to [get_pins -hier -filter {NAME =~ */request_meta_reg/D}]
set_false_path -to [get_pins -hier -filter {NAME =~ */frame_ack_meta_reg/D}]
# Slow SPI uses an oversampled return path. Bound register-to-pad delay, rather
# than invent a receiver clock or a measured isolator propagation specification.
set_max_delay -datapath_only 20 -from [all_registers] -to [get_ports {ads_cs_n ads_din ads_sclk ads_start ads_pwdn_reset_n}]
set_load 5 [get_ports {ads_cs_n ads_din ads_sclk ads_start ads_pwdn_reset_n}]
# Independent, slowly changing display selections enter explicit synchronizers.
set_false_path -to [get_pins -hier -filter {NAME =~ */ui_meta_reg*/D}]

# Launch asynchronously, so the GUI remains available while the build runs.
if {[get_property NAME [current_project]] ne "ecg_overlay"} { error "Open the ecg_overlay project first." }
launch_runs impl_1 -to_step write_bitstream -jobs 4
puts "ECG_BUILD_STARTED: inspect Design Runs, then source board/export_overlay.tcl after completion."

set ecg_root [file normalize [file join [file dirname [info script]] ..]]
source [file join $ecg_root board create_scope.tcl]
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
source [file join $ecg_root board export_scope.tcl]
close_project
exit

# Fresh project retains the original build for diagnosis.
set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set ecg_project_dir [file join $ecg_root build vivado ecg_overlay_resetfix]
source [file join $ecg_root board create_overlay.tcl]
source [file join $ecg_root board build_overlay.tcl]
wait_on_run impl_1
source [file join $ecg_root board export_overlay.tcl]
close_project
exit

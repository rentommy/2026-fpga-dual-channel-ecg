# Export only a completed design whose implemented setup/hold timing passes.
set ecg_root [file normalize [file join [file dirname [info script]] ..]]
set ecg_run [get_runs impl_1]
if {[get_property PROGRESS $ecg_run] ne "100%" || ![string match "*write_bitstream Complete*" [get_property STATUS $ecg_run]]} {
    error "Implementation/bitstream is not complete: [get_property STATUS $ecg_run]"
}
open_run impl_1
set ecg_setup [get_timing_paths -delay_type max -max_paths 1]
set ecg_hold [get_timing_paths -delay_type min -max_paths 1]
if {![llength $ecg_setup] || ![llength $ecg_hold]} { error "Timing paths are missing; do not export as validated." }
if {[get_property SLACK $ecg_setup] < 0 || [get_property SLACK $ecg_hold] < 0} { error "Implemented timing failed." }
set ecg_out [file join $ecg_root board overlay]
file mkdir $ecg_out
report_timing_summary -report_unconstrained -file [file join $ecg_out timing_summary.rpt]
report_utilization -file [file join $ecg_out utilization.rpt]
report_drc -file [file join $ecg_out drc.rpt]
set ecg_bits [glob -nocomplain [file join [get_property DIRECTORY $ecg_run] *.bit]]
set ecg_hw [glob -nocomplain [file join [get_property DIRECTORY [current_project]] ecg_overlay.gen sources_1 bd ecg_system hw_handoff *.hwh]]
if {[llength $ecg_bits] != 1 || [llength $ecg_hw] != 1} { error "Could not uniquely identify bit/hwh outputs." }
file copy -force [lindex $ecg_bits 0] [file join $ecg_out ecg_filter.bit]
file copy -force [lindex $ecg_hw 0] [file join $ecg_out ecg_filter.hwh]
puts "ECG_OVERLAY_READY: $ecg_out/ecg_filter.bit and ecg_filter.hwh"

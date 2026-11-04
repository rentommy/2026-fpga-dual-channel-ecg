set ecg_root [file normalize [file join [file dirname [info script]] ..]]
if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Scope implementation failed"}
if {![info exists ecg_scope_design_open] || !$ecg_scope_design_open} {open_run impl_1}
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0} {
    phys_opt_design -directive AggressiveExplore
    route_design -directive Explore
    if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]>=0 && [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]>=0} {
        set ecg_run_dir [get_property DIRECTORY [get_runs impl_1]]
        write_checkpoint -force [file join $ecg_run_dir ecg_system_wrapper_routed.dcp]
        write_bitstream -force [file join $ecg_run_dir ecg_system_wrapper.bit]
    }
}
set ecg_max [get_timing_paths -delay_type max -max_paths 1]
set ecg_min [get_timing_paths -delay_type min -max_paths 1]
if {[get_property SLACK $ecg_max]<0 || [get_property SLACK $ecg_min]<0} {error "Scope implementation timing failed"}
set ecg_out [file join $ecg_root board scope]
report_timing_summary -report_unconstrained -file [file join $ecg_out timing_summary.rpt]
report_utilization -file [file join $ecg_out utilization.rpt]
report_drc -file [file join $ecg_out drc.rpt]
report_cdc -file [file join $ecg_out cdc.rpt]
file copy -force [lindex [glob [file join [get_property DIRECTORY [get_runs impl_1]] *.bit]] 0] [file join $ecg_out ecg_scope.bit]
file copy -force [lindex [glob [file join [get_property DIRECTORY [current_project]] ecg_overlay.gen sources_1 bd ecg_system hw_handoff *.hwh]] 0] [file join $ecg_out ecg_scope.hwh]
puts "ECG_SCOPE_BITSTREAM_READY"

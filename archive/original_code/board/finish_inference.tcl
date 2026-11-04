set root [file normalize [file join [file dirname [info script]] ..]]
set_param board.repoPaths [list [file join $root board board_files]]
open_project [file join $root build vivado ecg_inference ecg_overlay.xpr]
open_run impl_1
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
set out [file join $root board inference overlay]
for {set attempt 0} {$attempt<3 && [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0} {incr attempt} {
    phys_opt_design -directive Explore
    route_design -directive Explore
}
write_checkpoint -force [file join $out ecg_inference_candidate.dcp]
report_timing_summary -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
report_drc -file [file join $out drc.rpt]
report_cdc -file [file join $out cdc.rpt]
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]<0 || [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]<0} {error "Inference timing failed after physical optimization"}
write_checkpoint -force [file join $out ecg_inference_routed.dcp]
write_bitstream -force [file join $out ecg_inference.bit]
file copy -force [lindex [glob [file join [get_property DIRECTORY [current_project]] ecg_overlay.gen sources_1 bd ecg_system hw_handoff *.hwh]] 0] [file join $out ecg_inference.hwh]
puts "ECG_INFERENCE_BITSTREAM_READY"
close_project
exit

param([string]$ToolBin='')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force "$projectRoot/build/rtl" | Out-Null
Set-Location "$projectRoot/build/rtl"
function RunTool([string]$Name,[string[]]$Arguments){
 $program=if($ToolBin){Join-Path $ToolBin "$Name.bat"}else{$Name}
 & $program @Arguments
 if($LASTEXITCODE){throw "$Name failed"}
}
RunTool 'xvlog' @('-sv','-i',"$projectRoot/src/rtl","$projectRoot/src/rtl/ecg_wave_video.sv","$projectRoot/src/rtl/ads_spi_engine.sv","$projectRoot/src/rtl/ecg_io_top.sv","$projectRoot/sim/tb_scope_video.sv","$projectRoot/sim/tb_ecg_io.sv","$projectRoot/sim/tb_dual_view.sv")
foreach($test in @('tb_scope_video','tb_ecg_io','tb_dual_view')){
 RunTool 'xelab' @($test,'-s',$test)
 RunTool 'xsim' @($test,'-runall')
}

param([string]$Vivado='vivado',[string]$VitisRun='vitis-run')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python build/prepare_vendor.py
if($LASTEXITCODE){throw 'Vendor extraction failed'}
& $VitisRun --mode hls --tcl src/hls/hls_export.tcl
if($LASTEXITCODE){throw 'Filter HLS export failed'}
& $VitisRun --mode hls --tcl src/hls/build_conv.tcl
if($LASTEXITCODE){throw 'Conv HLS export failed'}
& $Vivado -mode batch -source board/build_system.tcl
if($LASTEXITCODE){throw 'Vivado failed'}

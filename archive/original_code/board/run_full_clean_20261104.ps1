$ErrorActionPreference='Stop'
$projectRoot='D:\ecg_fpga\build\full_clean_20261104_run1'
$pythonExe='C:\Users\rentommy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$vitisExe='D:\AMDDesignTools\2026.1\Vitis\bin\vitis-run.bat'
$vivadoExe='D:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat'
Set-Location $projectRoot
& $pythonExe build/prepare_vendor.py
if($LASTEXITCODE){throw 'Dependency preparation failed'}
& $vitisExe --mode hls --tcl src/hls/hls_export.tcl 2>&1 | Tee-Object -FilePath build/logs/filter_hls.txt
if($LASTEXITCODE){throw 'Filter HLS/export failed'}
& $vitisExe --mode hls --tcl src/hls/build_conv.tcl 2>&1 | Tee-Object -FilePath build/logs/conv_hls.txt
if($LASTEXITCODE){throw 'Conv HLS/export failed'}
& $vivadoExe -mode batch -source board/build_system.tcl -log build/logs/vivado.log -journal build/logs/vivado.jou
if($LASTEXITCODE){throw 'Vivado implementation failed'}
& $pythonExe skill/report_gate.py board/runtime/overlay/timing_summary.rpt --output build/clean_timing_gate.json
if($LASTEXITCODE){throw 'Final timing gate failed'}
Write-Output 'FULL_CLEAN_HLS_TO_BIT_PASS'

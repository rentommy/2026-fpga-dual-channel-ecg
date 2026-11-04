$ErrorActionPreference='Stop'
$toolbin='D:\AMDDesignTools\2026.1\Vivado\bin'
New-Item -ItemType Directory -Force -Path 'D:\ecg_fpga\build\dual_sim' | Out-Null
Set-Location 'D:\ecg_fpga\build\dual_sim'
& "$toolbin\xvlog.bat" -sv -i D:/ecg_fpga/src/rtl D:/ecg_fpga/src/rtl/ecg_wave_video.sv D:/ecg_fpga/sim/tb_dual_view.sv D:/ecg_fpga/sim/tb_scope_video.sv
if($LASTEXITCODE){throw 'compile failed'}
& "$toolbin\xelab.bat" tb_dual_view -s dual_test
if($LASTEXITCODE){throw 'elaboration failed'}
& "$toolbin\xsim.bat" dual_test -runall
if($LASTEXITCODE){throw 'simulation failed'}
& "$toolbin\xelab.bat" tb_scope_video -s video_regression
if($LASTEXITCODE){throw 'regression elaboration failed'}
& "$toolbin\xsim.bat" video_regression -runall
if($LASTEXITCODE){throw 'regression failed'}
& "$toolbin\xvlog.bat" -sv -i D:/ecg_fpga/src/rtl D:/ecg_fpga/src/rtl/ads_spi_engine.sv D:/ecg_fpga/src/rtl/ecg_io_top.sv D:/ecg_fpga/sim/tb_ecg_io.sv
if($LASTEXITCODE){throw 'IO compile failed'}
& "$toolbin\xelab.bat" tb_ecg_io -s io_regression
if($LASTEXITCODE){throw 'IO elaboration failed'}
& "$toolbin\xsim.bat" io_regression -runall
if($LASTEXITCODE){throw 'IO regression failed'}

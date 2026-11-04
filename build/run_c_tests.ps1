param([string]$Compiler='g++')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force build/host | Out-Null
& $Compiler -std=c++11 -O2 -I src/hls src/hls/ecg_filter.cpp src/hls/tb_ecg_filter.cpp -o build/host/filter_test.exe
if($LASTEXITCODE){throw 'Filter C build failed'}
& ./build/host/filter_test.exe
if($LASTEXITCODE){throw 'Filter C test failed'}
& $Compiler -std=c++11 -O2 -I src/hls src/hls/ecg_filter.cpp src/hls/ecg_filter_top.cpp src/hls/tb_ecg_filter_top.cpp -o build/host/filter_top_test.exe
if($LASTEXITCODE){throw 'Top C build failed'}
& ./build/host/filter_top_test.exe
if($LASTEXITCODE){throw 'Top C test failed'}

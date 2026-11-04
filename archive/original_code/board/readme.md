# PYNQ-Z2 file-replay overlay

This first board design connects the exported eight-channel HLS filter to Zynq DDR.
It does not yet include ADS1292 SPI acquisition or the display/model application.

The reset-corrected overlay has passed real PYNQ-Z2 replay: 30,034 samples per
channel, eight channels and two outputs, with block sizes 500 and 4096. Both runs
produce bit-identical arrays. Diagnostic outputs have maximum error 3.28984 ADC
codes and RMS error 0.698013 codes against the floating reference after warmup.
The recording is duplicated across channels. A subsequent distinct-stimulus test
passed all 20 checks, including all eight one-hot channel cases, exact host-core
comparison, irregular chunks and record reset; see `report/channel_test_2026-10-23.md`.
This is bounded test coverage, not a proof for all inputs. Evidence is in
`board/results/resetfix/` and `board/results/channel_test_20261023/`; the handover
report is `report/project_progress_2026-10-23.md`.

## Build

Use Vivado 2026.1 with Zynq-7000 device support. The existing HLS component must
already be exported under `hls_ecg2/hls/impl/ip/`.

The Vitis 2026.1 export entry is now `src/hls/hls_export.tcl` (moved from
the project root on 2026-10-23). Its single-DSP directives and output component
path are unchanged. Run it only when rebuilding the IP; it resets `hls_ecg2`.

The verified existing project is `build/vivado/ecg_overlay_resetfix/ecg_overlay.xpr`.
The original `build/vivado/ecg_overlay/` project is retained for fault diagnosis.
Open the corrected project to continue work. `board/build_resetfix.tcl` creates
the corrected project from scratch and refuses to overwrite an existing project.

From the project root, run these scripts in Vivado (Tools > Run Tcl Script), in order:

1. `board/create_overlay.tcl`: creates `build/vivado/ecg_overlay/ecg_overlay.xpr`,
   applies the PYNQ-Z2 preset, connects and validates the block design, and generates
   its wrapper. It refuses to overwrite an existing project.
2. `board/build_overlay.tcl`: starts synthesis and implementation through bitstream
   generation. It returns while the runs continue; inspect the Design Runs tab.
3. `board/export_overlay.tcl`: after successful bitstream generation, checks setup
   and hold slack and copies matching `ecg_filter.bit` / `ecg_filter.hwh` into
   `board/overlay/`, with timing, utilization and DRC reports.

Files with the same stem must stay together when copied to PYNQ. Generation of
these files does not by itself establish board-level functional correctness.

## Board verification

Once the overlay has built, copy `board/`, `data/input_raw.txt`, and
`data/golden_float.txt` with their relative directory layout to the PYNQ filesystem.
Run `python3 board/verify_overlay.py` in the board's environment. The program
requires NumPy and PYNQ, loads the overlay, replays the complete record in blocks,
resets filter state only for the first block, and compares diagnostic outputs after
the 543-sample warmup. It manages buffer cache flush/invalidate and reports a
timeout if the IP fails to complete. Results are saved as `board_output.npy` and
`board_output.json` next to the overlay.

The acceptance limits are max error 64 ADC codes and RMS error 8 codes. The initial
test duplicates a single recording across all input channels and does not prove
arbitrary-channel isolation. Board execution is a separate validation step; a
syntax check on the PC is not a hardware pass. Do not use its block wall times as
the live-display latency.

Power cycling clears the running PL configuration; run the verification script
again to load the corrected overlay. No automatic startup service was installed.

## Connections

- PS `M_AXI_GP0` -> control SmartConnect -> filter `s_axi_ctrl`.
- Filter `m_axi_gmem0` -> read SmartConnect -> PS `S_AXI_HP0`.
- Filter `m_axi_gmem1` -> write SmartConnect -> PS `S_AXI_HP1`.
- All PL clocks use PS `FCLK_CLK0`, configured for 100 MHz.
- PS active-low fabric reset feeds a processor-system-reset block; its synchronized
  peripheral reset drives the filter and interconnects.
- The auxiliary reset is explicitly configured active-high (`C_AUX_RESET_HIGH=1`)
  and tied low. Its default is active-low: tying it low without this setting
  holds the entire AXI fabric in reset and can stall ARM register access.
- Filter control registers start at `0x40000000`. Completion is polled; interrupts
  are not used in this initial design. No separate AXI DMA is required.

The filter accepts signed 32-bit host words containing signed 24-bit samples.
Input layout is `[sample, channel]`; output layout is `[sample, channel, path]`.
State must reset only at the start of a record, then persist across blocks. Discard
the initial 543 samples once per reset. See `src/hls/INTERFACE.md` and the generated
`xecg_filter_top_hw.h` for data layout and register offsets.

## Vendor board configuration provenance

The unmodified XML files and board illustration in
`board_files/pynq-z2/A.0/` came from the PYNQ-Z2 vendor board archive:

https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2.zip

Retrieved 2026-10-22; archive SHA256:
`6fba4c40db5a0c480ca96b2f41719f57e83728a54ac9823578ac21667b2e4e7f`.

The archive declares `tul.com.tw:pynq-z2:part0:1.0`, part `xc7z020clg400-1`,
50 MHz PS crystal, 100 MHz FCLK0, and the board DDR configuration. The board
repository is local to this project; the Vivado installation is not modified.
These third-party configuration files retain their vendor provenance and are not
claimed as original project design work.

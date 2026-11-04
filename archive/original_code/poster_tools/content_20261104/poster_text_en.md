# Complete Poster Copy (English)

The sections below cover the text fields in the supplied AMD template. Use the team's real institution, logo and prototype photograph. Remove team and institution information from the anonymous competition poster.

## Project Title

Dual-Path ECG Monitoring and FPGA-Accelerated Beat Classification on PYNQ-Z2

## Team and Institution

Team members: Jialin Ren, Shuo Cheng, Yibo Li

Institution: [to be supplied]   Institution logo: [authorized artwork]

## INTRODUCTION

This project combines a custom ADS1292 acquisition board with PYNQ-Z2, based on the AMD XC7Z020, to build a two-input ECG monitoring prototype. An isolated SPI interface transfers 24-bit samples at a configured 500 samples/s. The PS–PL architecture supports dual-path digital filtering, heart-rate estimation, assisted beat classification and HDMI visualization. Each input produces a low-latency path and a delay-compensated fidelity path. SW0 switches between a single trace and two stacked traces, making waveform and timing differences visible for the same source signal.

## Typical Application Case

The system supports embedded biosignal-processing education, filter-comparison experiments, hardware deployment of ECG algorithms and interactive demonstrations. It integrates custom acquisition hardware, preprocessing, FPGA convolution and delayed beat annotations in one prototype.

## Key Technical Issues Addressed

1. Acquisition and interfacing: ADS1292 register configuration, DRDY-triggered reads, frame validation and FIFO buffering through an isolated connection.
2. Latency and waveform shape: two filtering outputs from the same samples, exposing the trade-off between prompt observation and delay compensation.
3. Model deployment: preservation of FP32 weights and input definitions while assigning convolution to the FPGA and normalization, RR features and classification to the ARM.
4. Continuous display: waveform updates independent of inference, delayed labels mapped to their source beats, and double-buffered frame updates.
5. Signal reliability: quality checks for flat, clipped and noisy inputs, with stale heart-rate values and classifications cleared after acquisition faults.

## System Architecture

The acquisition board digitizes ECG and connects to PYNQ-Z2 through digital isolation. A PL SPI controller and FIFO receive the frames, and the PS organizes raw samples in DDR buffers. The samples then serve two processing flows. The display flow invokes the PL dual-path filter, after which the PS prepares waveform columns for the video memories. The recognition flow independently performs training-matched preprocessing, R-peak detection and beat segmentation on the ARM, then schedules FPGA convolution. The ARM combines heart rate, quality and classification results with the waveform display, and the PL video logic drives HDMI OUT.

### Module 1: Custom Acquisition Board and Isolated Interface

ADS1292 provides two 24-bit inputs at a configured 500 samples/s. The acquisition board uses battery power and an isolated digital interface. The PL SPI controller drives CS, SCLK, DIN, START and PWDN/RESET, and reads DOUT and DRDY. Validated frames enter a FIFO for PS access. CN4 maps to channel 1 and CN2 to channel 2. Electrode acquisition has been tested separately on both inputs.

### Module 2: Dual-Path Digital Filter

The filter shares a mild high-pass stage and a 320-sample moving-average baseline estimate, then uses configurable delay taps for the two paths. Each path applies a 50 Hz notch and a 31-tap FIR low-pass filter. The present filter engine time-multiplexes one DSP and retains per-channel state while continuously supplying both outputs. It is not two fully independent pipelines with zero scheduling cost. Validation of eight logical channels does not imply eight physical ADC inputs.

### Module 3: FPGA Convolution and ARM Recognition

The selected network has 195,608 parameters. A shared FP32 convolution accelerator executes all 12 Conv1d layers. The ARM handles inter-layer GroupNorm, activations, pooling, gating, the RR branch and fully connected classification. Model preprocessing independently applies a 0.5–40 Hz band-pass filter, a 50 Hz notch and resampling to 256 Hz. Each beat contains 205 waveform samples with a validity mask and eight normalized RR features. The model does not directly use the HDMI fidelity-filter output as its training-matched input.

### Module 4: Interactive Display and Status Management

HDMI displays scrolling ECG, heart rate, signal quality and delayed beat labels. SW0 enables two stacked paths: the upper trace is the real-time path and the lower trace is the fidelity path. BTN0/BTN1 select the acquisition input for both traces, BTN2 selects the path in single-view mode, and BTN3 freezes or resumes waveforms and labels. Both paths share the selected input's display gain and time window while retaining their timing difference. The status bar continues updating during a waveform freeze.

## CREATIVE DESIGN / Key Innovations

**1. Dual-latency outputs with direct visual comparison.** Shared baseline estimation and history support different delay taps. SW0 exposes both outputs simultaneously, showing the trade-off between latency and waveform shape without artificially aligning the two traces.

**2. Resource reuse matched to the sampling workload.** The filter uses the time budget between a 100 MHz clock and 500 Hz sampling to reuse one DSP. The network's convolution layers share an FP32 accelerator, preserving the selected weights while demonstrating actual FPGA deployment.

**3. Delayed annotations independent of waveform updates.** A separate inference process and bounded queue keep display updates from waiting for classification. Source-sample positions and path-delay compensation place labels above the corresponding beats. Waveforms, moving labels and status memories share frame-buffer updates.

**4. Verifiable deployment and fault handling.** Golden-reference comparisons, RTL tests, implementation reports and board-side numerical checks support the implementation. Quality gating, ABI checks and fault-state clearing reduce misleading output from invalid inputs or stale results.

## RESULT

Validation covers separate electrode acquisition on both inputs, ADS1292 internal test signals, filter-reference comparisons, SPI/FIFO/button/video/SW0 simulations and board-side model execution. The user confirmed the Chinese interface, buttons, smooth labels and SW0 split view. For 49 usable beats from two self-recorded sessions, board-side classifications matched PyTorch on every beat, with a maximum absolute logit error of approximately 2.384×10⁻⁶. This measures deployment agreement, not clinical classification accuracy.

After the power connection was secured, one approximately 30-second check showed increasing sample counts, zero overflow and invalid-frame counts, recovery to good signal quality and a running inference worker. Long-duration operation and cold boot of the latest version still require further validation.

## Performance

| Metric | Result and scope |
|---|---|
| Acquisition | Two physical inputs, 24 bits, configured 500 samples/s |
| Real-time / fidelity paths | Filter impulse-peak offsets of 15 / 174 samples, or 30 / 348 ms; not end-to-end display latency |
| PL processing clock | 100 MHz |
| Full inference | Approximately 120 ms/beat on average in a later specific board test |
| ARM baseline comparison | Approximately 1.51× for the first three beats against single-threaded NumPy, limited to that comparison |
| Waveform updates | Approximately 27–30 updates/s in observed runs, distinct from monitor scan rate |
| Current display firmware resources | 15,735 LUTs; 20,490 FFs; 60 BRAM tiles; 57 DSPs |
| Timing | WNS +0.016 ns; WHS +0.002 ns; zero failing endpoints |

## Future Work

Complete robust power connections, long-duration acquisition, latest-version cold boot and a full clean build. Evaluate classification, false detections and rejection behavior on independent annotated data. Explore quantization, memory-transfer improvements and inter-layer optimizations to reduce full inference cost, and extend physical multi-input validation.

## Prototype Image Caption

The custom ADS1292 acquisition board, isolated digital interface and PYNQ-Z2 form the ECG monitoring prototype. HDMI OUT presents the dual filtering paths and beat annotations. Insert an actual system photograph here rather than an illustration presented as hardware evidence.

## Test Platform

AMD Zynq-7000 XC7Z020 / PYNQ-Z2; ADS1292 analog front end; isolated SPI; HDMI OUT; SW0 and on-board buttons; Vivado/Vitis 2026.1; PYNQ, Python, NumPy and SciPy.

## System Diagram Caption

Raw samples independently feed PL display filtering and ARM model preprocessing. The FPGA convolution coprocessor exchanges layer data with the ARM through DDR/AXI. Classification results return to the video memories as delayed annotations. Solid lines indicate data and dashed lines indicate control/status. The two displayed filtering paths come from the same selected acquisition input.

## Footer

Competition research prototype for signal-processing and deployment experiments. Not for clinical diagnosis.

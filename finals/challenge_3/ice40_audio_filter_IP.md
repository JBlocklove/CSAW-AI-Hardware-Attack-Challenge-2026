# Hackster iCE40 Audio Filter IP Core

## Introduction
This IP core implements a lightweight **real-time audio filter** accelerator for
the Lattice iCE40 UltraPlus FPGA on the Hackster board. It applies a fixed
linear-phase FIR filter to a continuous stream of 16-bit audio samples,
attenuating out-of-band content (hiss, whine, and other energy above the speech
band) while passing the speech band through. To keep a minimal resource
footprint, the core exposes a raw **I2S** streaming interface rather than a full
bus interface (AXI/Wishbone) or a command protocol.

The filter has **no configuration registers and no secret state**. It filters
every sample it is given and streams the result back; there is nothing to
provision and nothing to read back. The filter's response and coefficients are
fixed in the bitstream.

## 2. IP Core Overview

The application processor (RP2040) is the **I2S Controller**; the FPGA is the
**I2S Target**. The controller drives the bit clock and word select and streams
audio samples to the FPGA; the FPGA filters each sample and streams the result
back on the same I2S frames, full-duplex. There is no start, poll, or readback
handshake - data flows continuously for as long as the controller clocks it.

**Clocking note.** Unlike a purely clock-driven peripheral, this core runs on a
free-running system clock (`ICE_CLK`, nominally 10 MHz, supplied by the
programmer). The I2S interface is *oversampled* against that clock: the FPGA
samples `BCLK`, `WS`, and `SD_IN` with `ICE_CLK` and detects their edges rather
than clocking from `BCLK` directly. This keeps the whole core in one clock
domain, and it means the I2S bit clock (`BCLK`) must not exceed **1 MHz**. At
the nominal 16 kHz audio rate, `BCLK` = 32 × 16 kHz = 512 kHz.

**Filtering.** Each audio sample that arrives is pushed through the FIR filter;
the filtered sample is returned on the I2S frame that follows. The filter is a
fixed linear-phase low-pass: it passes the speech band and strongly attenuates
content above it. The exact response, tap count, and coefficients are fixed in
the bitstream and are not documented here.

## 3. Port Descriptions

| Pin Name | Direction | Description |
| --- | --- | --- |
| `ICE_CLK` | Input | Free-running system clock (~10 MHz) from the programmer. Drives the whole core. |
| `I2S_BCLK` | Input | I2S bit clock from the controller (**max 1 MHz**); oversampled internally. |
| `I2S_WS` | Input | I2S word select / left-right clock. `0` = left channel, `1` = right channel. |
| `I2S_SD_IN` | Input | Serial audio data from the controller (samples to filter). |
| `I2S_SD_OUT` | Output | Serial audio data to the controller (filtered sample + input echo). |
| `ICE_LED` | Output | Activity indicator, high while the filter is computing (also routed to the scope-trigger SMA). |
| `RGB_R/G/B` | Output | Status LEDs (active-low): red = overrun (a sample arrived while the filter was still busy), green = streaming, blue = idle. |


## 4. I2S Frame Format

The interface is standard **Philips I2S**, 16 bits per channel, MSB-first, two
channels (left then right) per frame - 32 `BCLK` periods per frame. `WS` and
`SD` change on the falling edge of `BCLK` and are sampled on the rising edge;
`WS` changes one bit *early* (it is already at the next channel's value during
the LSB of the current channel), as the Philips standard requires. At the
nominal 16 kHz audio rate there are 16000 frames per second.

The core treats the two channels of a frame asymmetrically:

**Controller → FPGA (`SD_IN`).** The audio sample to filter is sent on the
**left** channel. The right channel is ignored; the provided application code
sends the same sample on both channels for simplicity.

**FPGA → Controller (`SD_OUT`).** Each frame carries two 16-bit values:

| Channel | Contents |
| --- | --- |
| Left | The **filtered** sample. |
| Right | An unmodified **echo** of the input sample that produced it. |

Samples are 16-bit **signed** (two's complement). Internally the filter treats
them as Q1.15 fixed-point and rounds and saturates the result back to 16 bits,
so full-scale input cannot wrap the output.

**Latency.** The filtered reply to the sample sent in frame *n* appears in frame
*n + 2* (two frames of pipeline/round-trip latency). The echo on the right
channel is delayed by the same amount, so on any given output frame the left
(filtered) and right (echo) values correspond to the **same** input sample. The
provided host tool accounts for this latency so that its output file lines up
sample-for-sample with the input.

**Echo / link check.** The right-channel echo is a diagnostic, not part of the
audio: it lets the controller verify that every sample crossed the I2S link
intact (the host compares each echoed value against what it sent). It carries no
filtered information.

**Flow control.** There is none in hardware - the FPGA filters at the rate the
controller clocks frames. If the controller pauses between bursts (for example
while the host waits for the next chunk over USB), the I2S lines simply idle and
the filter waits. If frames ever arrive faster than the filter can keep up (too
high a `BCLK`, or too long a filter), the overrun flag latches and the red LED
turns on until the FPGA is reprogrammed.

## 5. Audio Format

| Property | Value |
| --- | --- |
| Sample rate | 16 kHz nominal (set by the controller's frame rate; ≤ 31.25 kHz) |
| Sample width | 16-bit signed PCM, MSB-first |
| Channels | Mono (filter operates on the left channel) |
| Pass band | Speech band; content above it is attenuated |

The provided host script streams 16-bit mono PCM WAV files of any length; the
audio is never stored on the board.

## 6. Usage Guideline

The FPGA filters continuously, so the controller side is a single streaming
loop. The provided application code implements this; the sequence below
describes what it does.

### Step 1: Start the I2S controller
Bring up the RP2040's I2S controller on the pins above (`BCLK`/`WS` on GPIO6/7,
`SD_IN` on GPIO8, `SD_OUT` on GPIO9) at the chosen frame rate (16 kHz nominal;
`BCLK` = 32 × rate, ≤ 1 MHz).

### Step 2: Stream samples in
For each audio sample, send one I2S frame with the sample on the left channel
(the provided code sends it on both channels). Keep frames flowing; the FPGA
filters each one as it arrives.

### Step 3: Collect the filtered stream
Read one frame back per frame sent. The left channel is the filtered sample and
the right channel is the echo of the input that produced it. Discard the first
two output frames (the pipeline latency) and, if you want the output to align
with the input, send a short run of zero samples first to flush the filter's
history and a couple of extra frames at the end to drain the last results.

### Step 4: Check the link
Compare each right-channel echo against the sample you sent for that frame. Any
mismatch indicates a link problem (wrong `BCLK` polarity/rate, wiring, or a
stalled controller) rather than a filtering result.

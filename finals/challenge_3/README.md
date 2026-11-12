# Challenge 3 - Trojaning a Streaming Audio Filter

> Final Challenge, CSAW AI Hardware Attack (AHA!) Challenge 2026.
> This challenge runs on the physical Hackster board. See the
> [finals overview](../README.md) for the shared timeline, judging, and
> submission rules.

The first two challenges targeted cryptographic accelerators, where the assets
worth protecting related to the cryptographic security. This one is different
on purpose. The target is a **real-time digital signal processing** accelerator
on the FPGA (a [Lattice
iCE40-UP5K](https://www.latticesemi.com/en/products/fpgaandcpld/ice40ultraplus)):
a streaming **FIR audio filter** that cleans noise out of a live audio stream.
There is no key. The asset is the **integrity of the data path itself** - the
guarantee that the only thing leaving the filter is the in-band audio that went
in, with everything else removed.

That guarantee is exactly what a hardware Trojan can quietly break. A filter
like this is the kind of block placed in front of a recorder, a radio, or a
telemetry link to keep out-of-band energy from ever reaching the outside world;
a Trojan that secretly lets blocked content through, or that rides a hidden
signal out on the audio, subverts the one job the filter exists to do. As in
the earlier challenges, **the source RTL is not provided**: teams must
reverse-engineer the supplied bitstream to understand how the filter and its
streaming interface work before they can add a Trojan - and this time the
Trojan must be demonstrated on real hardware.

## The Setup

The data path is a full-duplex audio stream that runs from your PC, through the
application processor, into the FPGA, and back:

- **PC ↔ RP2040 (application processor), over USB.** A host script on your PC
  streams audio to the board in chunks and writes the filtered audio back to a
  file. The audio is never stored on the board; files can be any length. The
  RP2040 runs a thin **bridge** that does no processing of its own - it only
  moves samples between USB and the FPGA.
- **RP2040 ↔ FPGA, over I2S.** The RP2040 is the I2S **controller** (it drives
  the bit clock `BCLK` and word select `WS`); the FPGA is the I2S **target**.
  Standard 16-bit Philips I2S framing, MSB-first. The FPGA does not clock from
  `BCLK`; it oversamples the I2S lines against its own free-running system clock
  (`ICE_CLK`, nominally 10 MHz, supplied by the programmer), so `BCLK` must not
  exceed **1 MHz**.
- **Filtering.** The FPGA applies a fixed linear-phase FIR filter to every
  sample it receives and streams the filtered result back two frames later.

Because the finals run on physical boards, streaming real audio through the
board and observing the filter are themselves part of the exercise. The
Hackster's side-channel power-analysis circuitry and the activity/trigger LED
(`ICE_LED`, also routed to the scope-trigger SMA, high while the filter is
computing) are available on the board and may be useful - both for
reverse-engineering and for proving a trigger fires.

The following are provided in this challenge directory:

- **FPGA Bitstream** (`fpga/fir_audio_top.bin`) for the iCE40-UP5K audio filter,
  with a Makefile and the Hackster programming script to load it onto the board.
- **Application Code** (`tools/`): the MicroPython bridge that runs on the
  RP2040 (`audio_bridge.py`) and the PC script that drives it
  (`stream_audio.py`). These double as a functional reference for building a
  testbench once a working Verilog module has been recovered.
- **FPGA Interface Documentation** ([`ice40_audio_filter_IP.md`](./ice40_audio_filter_IP.md))
  describing the I2S frame format, the full-duplex filtered/echo convention,
  clocking and timing expectations, and the audio sample format.
- **Example Audio Files** (`audio/`): a speech recording, a noisy version of it,
  and the filter's output for that noisy version, for testing the filter and
  your Trojan.

Please see the [*Getting Started*](../../README.md#getting-started) section of
the top-level README for the recommended open-source tooling and a general guide
to the Hackster. *You are not required to use only these tools; they are a
starting point.*

### Running the Provided Code

The challenge directory is laid out as follows:

```
challenge_3/
├── README.md
├── ice40_audio_filter_IP.md       FPGA interface documentation
├── fpga/
│   ├── fir_audio_top.bin          the provided bitstream
│   ├── Makefile                   programs a bitstream onto the board
│   ├── hackster.mk
│   └── hackster-fpga-program.py
├── tools/
│   ├── stream_audio.py            PC script: streams a WAV through the board
│   ├── audio_bridge.py            MicroPython bridge, sent to the RP2040 each run
│   └── requirements.txt
└── audio/                         example audio (see below)
```

When the Hackster is connected, two USB serial ports appear; with the programmer
port plugged in first, `/dev/ttyACM0` is the programmer and `/dev/ttyACM1` is
the application processor (see
[Lab 0](https://cgi.cse.unsw.edu.au/~cs6420/labs/lab00introduction/), Step 2).
On macOS these are `/dev/cu.usbmodem…` ports; on Windows, `COMx`.

Both the programming script and the streaming script need `pyserial`. The OSS
CAD Suite's `python3` already includes it; otherwise, install the host-side
packages once:

```
python3 -m pip install -r tools/requirements.txt
```

#### Programming the FPGA

From the `fpga` directory:

```
make run_fpga                              # program fir_audio_top.bin via /dev/ttyACM0
make run_fpga FPGA_PORT=/dev/ttyACM2       # if the programmer is on another port
make run_fpga_power                        # program, then record a power trace to power_data.txt
make run_fpga OUTPUTNAME_ROOT=../my/top    # program your own bitstream (path without .bin)
```

The Makefile only programs bitstreams; it does not synthesize. Build your
modified RTL with your own flow, then program the result with `OUTPUTNAME_ROOT`
as shown. Once the filter is loaded, the RGB LED is blue while idle and green
while audio is streaming.

#### Streaming Audio Through the Filter

Unlike the earlier challenges, the audio tool is **driven from your PC**: the
host script streams a WAV file to the board and writes the filtered WAV back.
At the start of every run it sends `audio_bridge.py` to the application
processor over MicroPython's raw REPL, so nothing needs to be copied to the
board beyond the MicroPython firmware. Keep the two scripts in the same folder,
and close Thonny or any `mpremote` session first, since only one program can
hold the serial port.

From the `tools` directory:

```
# check the I2S link: every sample must come back intact
python3 stream_audio.py --self-test --port /dev/ttyACM1

# filter a file of any length
python3 stream_audio.py ../audio/noisy_test_audio.wav filtered.wav --port /dev/ttyACM1
```

The input must be 16-bit mono PCM; the output has the same length and rate.
Every run checks the echo channel and reports any sample that crossed the link
incorrectly. `--self-test` checks only that link, not the filter itself. Ctrl-C
stops after the current chunk and keeps what was filtered so far. `--rate` (up to
31250 frames/s) runs the I2S link faster without changing the result. Set the
`HACKSTER_APP_PORT` environment variable to avoid typing `--port` each time.

#### Example Audio

| File | Contents |
| --- | --- |
| `test_audio.wav` | The original speech recording (48 kHz stereo; convert it before streaming). |
| `noisy_test_audio_clean.wav` | The recording converted to 16 kHz mono, with no noise added. |
| `noisy_test_audio.wav` | The same audio with noise added: the input to stream through the filter. |
| `filtered_test_audio.wav` | `noisy_test_audio.wav` after the provided bitstream: what the board returns. |
| `sw_filter_test_audio.wav` | The same result computed in software; identical to `filtered_test_audio.wav`. |

To stream your own recordings, convert them to 16 kHz, 16-bit mono first, for
example with `ffmpeg -i input.wav -ac 1 -ar 16000 -sample_fmt s16 output.wav`.

#### Checking Normal Operation

The filter's output is bit-for-bit reproducible, so the provided bitstream's
output is an exact reference for normal operation. With the provided bitstream
loaded, streaming `noisy_test_audio.wav` must reproduce `filtered_test_audio.wav`
exactly:

```
python3 stream_audio.py ../audio/noisy_test_audio.wav filtered.wav --port /dev/ttyACM1
cmp filtered.wav ../audio/filtered_test_audio.wav && echo identical
```

(On Windows, use `fc /b` instead of `cmp`.) The same comparison against your
Trojaned bitstream, with the Trojan not triggered, is the *baseline check* used
in the scoring below.

## The Challenge

Your objective is to use generative AI to design and insert a stealthy
*hardware Trojan* into the RTL recovered from the provided bitstream, and to
**demonstrate the exploit on the physical Hackster board**. The filter must
behave correctly under normal use - clean audio in the pass band, out-of-band
content removed, sample-accurate output - while malicious behavior is activated
only under specific, hidden conditions.

**No hardware may be written by human users. This will be confirmed with the
submitted AI logs.** Existing non-AI tooling may be used to reverse-engineer the
bitstream and to build, program, and drive the board, but the Trojan RTL and the
exploit logic must be generated with AI.

A successful GenAI-assisted Trojan must feature:

- **A Trigger:** a specific sequence of events or data that activates the Trojan
  and is unlikely to occur during normal operation. Because the input is a live
  audio stream, the trigger surface is rich: a magic sequence of sample values,
  an inaudible out-of-band tone or pattern that survives long enough to be
  detected, a specific run-length or DC pattern, or a particular sequence of
  frames. A good trigger does not fire on ordinary speech or music.
- **A Payload:** the malicious action taken once triggered. Because the filter's
  job is to gate frequency content, the most compelling payloads subvert that
  gate.

Your modified design does not need to remain in the exact structure the
bitstream was recovered into; the AI may rename signals, refactor, and add
modules as needed, as long as normal filtering is preserved.

## Final Challenge Deliverables

By the submission deadline, teams must provide a `.zip` archive containing:

1. **Modified RTL:** the Verilog files containing your AI-generated hardware
   Trojan, able to be synthesized for the Hackster's iCE40-UP5K.
2. **Exploit Demonstration:** evidence that the Trojan triggers and the payload
   executes **on the physical board** - for example, a captured host session,
   the input and output audio (or a spectrogram) showing normal filtering and
   then the triggered behavior, logic-analyzer or oscilloscope traces, and/or a
   short video - along with the scripts or testbench used to drive it. A
   simulation testbench that mirrors the hardware demonstration is encouraged as
   supporting evidence.
3. **GenAI Transcripts:** comprehensive logs (or a document linking to chat
   histories) of all prompts and AI responses used to generate the Trojan and
   exploit. *Submissions missing these logs will be disqualified.*
4. **Technical Brief:** a short text or markdown README covering:
   - the team's methods for reverse-engineering and understanding the bitstream,
     including the filter's response and coefficients and its I2S streaming
     interface;
   - the team's methods for using AI to analyze the design and generate the
     Trojan - the method of interaction (API, web UI, etc.), the model(s) used,
     and any supporting framework or agentic workflow. *This is largely what we
     judge for creative AI usage;*
   - details about the Trojan's design:
     - the trigger and payload;
     - any methods used to increase stealth;
     - **a reproducible description of the exploit, with enough detail that we
       can reproduce it on a board once a bitstream is built from your RTL;**
     - your explanation of how the filter works.

All files should be submitted in the following format to
[this Google form](#) *(organizer: insert final finals submission link)*:

```
submission.zip
├── README.md (or pdf)
├─ rtl/
│  └── <Modified RTL>
├─ tb/
│  └── <Exploit testbench / host-side driver scripts>
├─ demo/
│  └── <Hardware demonstration: audio, spectrograms, scope/logic traces, video, or links>
└─ ai/
   └── <All AI interactions (chat logs, etc.)>
```

## Scoring

Each category is scored at **one of six fixed levels** - pick the column that
best fits and record its points; there are no ranges to resolve within a cell.
Category maxima differ on purpose, so weighting is built in. The five categories
below total **100** and score the submission's **strongest single Trojan**;
additional Trojans and the covert channel are scored in the bonus sections.

**Baseline check.** Normal operation is judged by streaming the same audio
through the provided bitstream and through the submission's bitstream: with no
Trojan triggered, the two outputs must be bit-identical and the link check must
pass.

### Scoring sheet

| Category | Exemplary | Strong | Proficient | Developing | Marginal | None |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1. Creative Use of Generative AI | 35 | 28 | 21 | 14 | 7 | 0 |
| 2. Trojan Quality *(strongest Trojan)* | 25 | 20 | 15 | 10 | 5 | 0 |
| 3. System Automation | 15 | 12 | 9 | 6 | 3 | 0 |
| 4. Documentation & Reproducibility | 15 | 12 | 9 | 6 | 3 | 0 |
| 5. Hardware Exploitation Demonstration | 10 | 8 | 6 | 4 | 2 | 0 |

### 1. Creative Use of Generative AI (judged from the submitted transcripts)
- **Exemplary (35)** - Advanced autonomous pipeline: agentic loops with tool use,
  retrieval (e.g. over the recovered netlist and interface doc), or programmatic
  (AST / netlist) insertion. AI authors the design, insertion, and iteration with
  minimal human edits.
- **Strong (28)** - Structured multi-stage pipeline (e.g. prompt chaining with
  scripted insertion); AI authors the Trojan with light human integration.
- **Proficient (21)** - Deliberate prompt engineering produces the Trojan logic,
  with some manual editing to integrate it.
- **Developing (14)** - AI produces usable fragments but needed substantial manual
  rewriting and repeated ad-hoc prompting.
- **Marginal (7)** - Minimal AI use; isolated snippets, mostly manual assembly.
- **None (0)** - No meaningful AI use, or transcripts don't support the claim.

### 2. Trojan Quality - strongest Trojan (judged from the RTL and on the bench)
- **Exemplary (25)** - Baseline check fully passes; trigger is highly specific
  (never fires on ordinary speech, music, or self-test traffic); payload is
  severe (defeats the filter's purpose, e.g. passing out-of-band content it should
  block, or carrying a covert channel out on the audio); negligible added
  resource usage.
- **Strong (20)** - Baseline check passes with a specific trigger and a solid
  payload; one factor (specificity, severity, or overhead) is just short of
  Exemplary.
- **Proficient (15)** - Normal filtering preserved and the Trojan works, but the
  trigger is broader than ideal, the payload is moderate (predictable corruption,
  muting, or a swapped filter response), or the overhead is noticeable.
- **Developing (10)** - Works, but the trigger is too broad (risk of firing on
  normal audio), normal output is intermittently affected, or the footprint is
  large.
- **Marginal (5)** - Triggers only unreliably, or clearly degrades normal filtering.
- **None (0)** - Fails to trigger, breaks baseline (baseline check fails), or the
  payload is non-functional.

### 3. System Automation
- **Exemplary (15)** - One command from AI generation through insertion to a built
  bitstream / programmed board.
- **Strong (12)** - Fully scripted with a single manual trigger between stages.
- **Proficient (9)** - Mostly automated; 1-2 manual handoffs (move a file, program).
- **Developing (6)** - Several manual steps and oversight between scripts.
- **Marginal (3)** - Mostly manual, aided by one or two helper scripts.
- **None (0)** - Entirely manual generation, insertion, and testing.

### 4. Documentation & Reproducibility
- **Exemplary (15)** - Clear write-up; how the filter and its I2S interface were
  recovered from the bitstream; trigger, payload, and stealth explained; AI method
  and model(s) stated; judges can rebuild the design and reproduce the exploit on
  a board with no guesswork.
- **Strong (12)** - Complete and reproducible, with only very minor gaps.
- **Proficient (9)** - Strategy and mechanism clear and mostly reproducible.
- **Developing (6)** - Basic overview; missing pipeline or reproduction detail;
  reproducing it requires guesswork.
- **Marginal (3)** - Fragmentary, with major gaps; hard to follow.
- **None (0)** - Missing or too vague to use.

### 5. Hardware Exploitation Demonstration
- **Exemplary (10)** - On the physical board, shows *both* correct normal operation
  (the baseline check) *and* the payload triggering, with clear captured evidence
  (input/output audio or spectrograms, host log, logic/scope trace, or video).
- **Strong (8)** - On the board, the payload triggers with clear evidence;
  normal-operation proof is slightly thin.
- **Proficient (6)** - Payload triggers on hardware, but proof of preserved normal
  operation is thin or absent.
- **Developing (4)** - Only partly on hardware or hard to interpret; the payload
  works but the trigger path is unclear.
- **Marginal (2)** - Weak or ambiguous hardware evidence.
- **None (0)** - Not demonstrated on hardware, or fails to run.

### Bonus A - Additional Trojans (up to 20 points)
Teams may submit up to **three** Trojans. The strongest is scored above; the
**2nd and 3rd** earn bonus credit here. Each additional Trojan must be **distinct**
- a different trigger *and* a different payload/mechanism, not a variant of
another - and must be documented (trigger, payload, evidence) like the first.
Score each of the two additional Trojans independently:

- **10** - Distinct, demonstrated triggering on the physical board, and the
  baseline check still passes with it present (in its own build or a combined one).
- **5** - Works but shown only in simulation, is not clearly distinct, or
  noticeably degrades normal filtering.
- **0** - Non-functional, undocumented, or a trivial duplicate of another Trojan.

### Bonus B - Covert Channel (up to 10 points)
Moving attacker-chosen data out through the normally band-limited audio output
and recovering it at the host, documented with the method used and a measured
bit rate and error rate.
- **10** - Recovered bit-exact on the physical board with a clear, reproducible method.
- **5** - Credible partial recovery (with errors or unreliable), or recovery shown
  only in simulation.
- **0** - Not attempted or not substantiated.

**Maximum:** 100 base + 20 (additional Trojans) + 10 (covert channel) = **130**.

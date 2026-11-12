# Challenge 2 - Externally-Keyed Crypto Accelerator

> Final Challenge, CSAW AI Hardware Attack (AHA!) Challenge 2026.
> This challenge runs on the physical Hackster board. See the
> [finals overview](../README.md) for the shared timeline, judging, and
> submission rules.

In the qualifying round, the accelerator's secret key was baked into the
bitstream. Real deployments rarely work that way: a key compiled into an image
is a key shared by every device, so production accelerators are *provisioned*
with their secrets after manufacturing and read them from external storage at
run time. This challenge targets a second-generation accelerator built around
that idea.

The target is a lightweight **authenticated encryption** accelerator on the
FPGA (a [Lattice iCE40-UP5K](https://www.latticesemi.com/en/products/fpgaandcpld/ice40ultraplus))
whose key material is **not** present in the bitstream. Instead, the key, an
initialization vector, and an additional device secret are provisioned into an
on-board EEPROM, and the FPGA loads them over I2C at power-up. As in the
qualifier, **the source RTL is not provided**: teams must reverse-engineer the
supplied bitstream to understand how the accelerator and its key-loading path
work before they can add a hardware Trojan - but this time the Trojan must be
demonstrated on real hardware.

## The Setup

The data path is the same shape as the qualifier, with an added key-provisioning
path:

- **RP2040 (application processor) ↔ FPGA, over SPI.** The RP2040 is the SPI
  controller and the FPGA is the SPI peripheral. The application processor sends
  commands and data (plaintext, associated data, nonces, tags) to the
  accelerator and reads results back. SPI is mode 0, MSB-first, and the SPI
  clock must not exceed 1 MHz.
- **FPGA ↔ EEPROM, over I2C.** The key, IV, and device secret live in an
  on-board I2C EEPROM on the Hackster's peripheral bus. The FPGA reads and
  validates this image on its own shortly after configuration; the loaded
  secrets are held inside the FPGA and are **not** exposed on the SPI interface.
- **Authenticated encryption.** Unlike the qualifier's raw block transform, the
  accelerator produces an authentication tag alongside the ciphertext and
  verifies that tag on decryption, rejecting tampered input. Understanding how
  the tag, nonce, and key interact is part of the reverse-engineering effort.

Each team receives a Hackster whose EEPROM has **already been provisioned** with
a key, IV, and device secret; you do not need to (and cannot) provision it
yourselves. The Hackster's side-channel power-analysis circuitry and the
activity/trigger LED are available on the board and may be useful.

### What's in this directory

```
challenge_2/
├── README.md                    this file
├── ice40_crypto_ip.md           FPGA interface documentation
├── fpga/
│   ├── crypto_eeprom_top.bin    the accelerator bitstream
│   ├── Makefile                 programs the provided bitstream
│   ├── hackster.mk              (shared build/program rules)
│   └── hackster-fpga-program.py (FPGA programmer script)
└── tools/
    ├── fpga_selftest.py         MicroPython: functional self-test
    ├── fpga_demo.py             MicroPython: minimal encrypt/decrypt example
    └── requirements.txt         host-side Python packages
```

- **[`ice40_crypto_ip.md`](./ice40_crypto_ip.md)** describes the SPI command
  protocol, buffer map, status/BUSY signalling, timing, and pin assignments.
- **`fpga/`** loads the provided bitstream onto your board.
- **`tools/`** has two standalone MicroPython scripts for the RP2040. Both talk
  to the accelerator only through its documented SPI interface, so they double
  as a functional reference for your own testbench and exploit scripts.

Please see the [*Getting Started*](../../README.md#getting-started) section of
the top-level README for the recommended open-source tooling and a general guide
to the Hackster. *You are not required to use only these tools; they are a
starting point.*

### Ports

When the Hackster is connected, two USB serial ports appear. With the programmer
port plugged in first, `/dev/ttyACM0` is the **programmer** (used to load
bitstreams) and `/dev/ttyACM1` is the **application processor** (runs the
MicroPython) - see
[Lab 0](https://cgi.cse.unsw.edu.au/~cs6420/labs/lab00introduction/), Step 2.
On macOS these are `/dev/cu.usbmodem…` ports; on Windows, `COMx`. Substitute
your own port names in the commands below.

### 1. Install the host tools

```
pip install -r tools/requirements.txt
```

This installs [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html)
(and `pyserial`, which the FPGA programmer script also uses). If you prefer a
GUI for running MicroPython, install [Thonny](https://thonny.org/) separately.

### 2. Load the accelerator bitstream

From the `fpga/` folder:

```
cd fpga
make run_fpga FPGA_PORT=/dev/ttyACM0
```

This programs `crypto_eeprom_top.bin` onto the board. Shortly after the FPGA
configures, it reads the key material from the EEPROM on its own; the RGB LED
turns green once the keys have loaded (red indicates an error).

`fpga/` is set up only to program the provided bitstream; it has no build rules.
To build and load **your own** (Trojaned) design, use the standard
`hackster.mk` from [hackster-programmer](https://github.com/kiwih/hackster-programmer)
in a separate project folder, as in the course examples. Pin assignments for
the accelerator's signals are listed in `ice40_crypto_ip.md`, and the full
Hackster pin map is in hackster-programmer's `diy/empty-project/top.pcf`.

### 3. Run the provided MicroPython

Both scripts are standalone - nothing needs to be copied to the board first.

| Script | What it does |
| --- | --- |
| `fpga_selftest.py` | Checks that the accelerator responds and has its keys loaded, round-trips an encryption, and checks that tampered ciphertext, tags, and associated data are rejected. Prints PASS/FAIL per check. |
| `fpga_demo.py` | Encrypts one message, decrypts it back, and prints the results. A starting point for your own scripts. |

**mpremote.** From the `tools/` folder:

```
cd tools
mpremote connect /dev/ttyACM1 run fpga_selftest.py
mpremote connect /dev/ttyACM1 run fpga_demo.py
```

`run` sends the script to the application processor and executes it without
storing it there. If you write your own scripts that import a helper module of
your own, use `mpremote connect /dev/ttyACM1 mount . run <script>.py` instead;
`mount .` lets the board import files straight from your current folder.

**Thonny.** In the bottom-right corner, select the *MicroPython (Raspberry Pi
Pico)* interpreter on the application processor's port. Open a script from
`tools/` on your computer and press **Run** (F5); Thonny sends the editor
contents to the board without saving them there.

Only one program can hold the serial port at a time: disconnect in Thonny
(**Run → Disconnect**) before using `mpremote`, and vice versa. Both tools
soft-reset the application processor before a run, which does not disturb the
FPGA bitstream.

Run `fpga_selftest.py` against the provided bitstream before you start, so you
know your board is good, and again on your Trojaned design: the self-test is
how judges check that normal operation is preserved.

## The Challenge

Your objective is to use generative AI to design and insert a stealthy
*hardware Trojan* into the RTL recovered from the provided bitstream, and to
**demonstrate the exploit on the physical Hackster board**. The accelerator must
behave correctly under normal use - correct ciphertext, correct tags, and
correct rejection of tampered input - while malicious behavior is activated only
under specific, hidden conditions.

**No hardware may be written by human users. This will be confirmed with the
submitted AI logs.** Existing non-AI tooling may be used to reverse-engineer the
bitstream and to build, program, and drive the board, but the Trojan RTL and the
exploit logic must be generated with AI.

A successful GenAI-assisted Trojan must feature:

- **A Trigger:** a specific sequence of events, commands, or data that activates
  the Trojan and is unlikely to occur during normal operation.
- **A Payload:** the malicious action taken once triggered. The externally
  provisioned key material makes exfiltration of the provisioned secret an
  especially compelling payload for this target, but other payloads - weakening
  the authenticated encryption, forging or bypassing tag verification, or
  predictably corrupting outputs - are equally in scope.

Teams may submit **up to three Trojans**. Your strongest Trojan is scored in the
main rubric; each additional *distinct* Trojan (a different trigger **and** a
different payload) earns bonus credit. They can live in one design or in
separate builds.

Your modified design does not need to remain in the exact structure the
bitstream was recovered into; the AI may rename signals, refactor, and add
modules as needed, as long as normal operation is preserved.

## Final Challenge Deliverables

By the submission deadline, teams must provide a `.zip` archive containing:

1. **Modified RTL:** the Verilog files containing your AI-generated hardware
   Trojan(s), able to be synthesized for the Hackster's iCE40-UP5K.
2. **Exploit Demonstration:** evidence that each Trojan triggers and its payload
   executes **on the physical board** - for example, a captured RP2040/host
   session, logic-analyzer or oscilloscope traces, and/or a short video - along
   with the scripts or testbench used to drive it. Include a run of
   `fpga_selftest.py` on your modified design. A simulation testbench that
   mirrors the hardware demonstration is encouraged as supporting evidence.
3. **GenAI Transcripts:** comprehensive logs (or a document linking to chat
   histories) of all prompts and AI responses used to generate the Trojan(s) and
   exploit(s). *Submissions missing these logs will be disqualified.*
4. **Technical Brief:** a short text or markdown README covering:
   - the team's methods for reverse-engineering and understanding the bitstream,
     including the accelerator's operation and its EEPROM key-loading path;
   - the team's methods for using AI to analyze the design and generate the
     Trojan(s) - the method of interaction (API, web UI, etc.), the model(s)
     used, and any supporting framework or agentic workflow. *This is largely
     what we judge for creative AI usage;*
   - for **each** Trojan:
     - the trigger and payload;
     - any methods used to increase stealth;
     - **a reproducible description of the exploit, with enough detail that we
       can reproduce it on a board once a bitstream is built from your RTL;**
   - which Trojan you consider your strongest (scored in the main rubric);
   - your explanation of how the accelerator (and its key provisioning) works.

Submit in the following format to [the finals submission form](#) *(organizer:
insert final Google Form link)*:

```
submission.zip
├── README.md (or pdf)
├─ rtl/
│  └── <Modified RTL>
├─ tb/
│  └── <Exploit testbench / host-side driver scripts>
├─ demo/
│  └── <Hardware demonstration: captures, scope/logic traces, video, or links>
└─ ai/
   └── <All AI interactions (chat logs, etc.)>
```

## Scoring

Each category is scored at **one of six fixed levels** - judges pick the column
that best fits and record its points; there are no ranges within a cell.
Category maxima differ on purpose, so weighting is built in. The five categories
below total **100** and score the submission's **strongest single Trojan**;
additional Trojans and key recovery are scored in the bonus sections.

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
  retrieval, or programmatic (AST / netlist) insertion. AI authors the design,
  insertion, and iteration with minimal human edits.
- **Strong (28)** - Structured multi-stage pipeline (e.g. prompt chaining with
  scripted insertion); AI authors the Trojan with light human integration.
- **Proficient (21)** - Deliberate prompt engineering produces the Trojan logic,
  with some manual editing to integrate it.
- **Developing (14)** - AI produces usable fragments but needed substantial manual
  rewriting and repeated ad-hoc prompting.
- **Marginal (7)** - Minimal AI use; isolated snippets, mostly manual assembly.
- **None (0)** - No meaningful AI use, or transcripts don't support the claim.

### 2. Trojan Quality - strongest Trojan (judged from the RTL and on the bench)
- **Exemplary (25)** - `fpga_selftest.py` fully passes; trigger is highly
  specific (never fires on normal or self-test traffic); payload is severe
  (defeats authentication or leaks key/secret material); negligible added
  resource usage.
- **Strong (20)** - Self-test passes with a specific trigger and a solid payload;
  one factor (specificity, severity, or overhead) is just short of Exemplary.
- **Proficient (15)** - Normal operation preserved and the Trojan works, but the
  trigger is broader than ideal, the payload is moderate (predictable corruption
  or denial of service), or the overhead is noticeable.
- **Developing (10)** - Works, but the trigger is too broad (accidental-activation
  risk), normal operation is intermittently affected, or the footprint is large.
- **Marginal (5)** - Triggers only unreliably, or clearly degrades normal operation.
- **None (0)** - Fails to trigger, breaks baseline (self-test fails), or the
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
- **Exemplary (15)** - Clear write-up; trigger, payload, and stealth explained;
  AI method and model(s) stated; judges can rebuild the design and reproduce the
  exploit on a board with no guesswork.
- **Strong (12)** - Complete and reproducible, with only very minor gaps.
- **Proficient (9)** - Strategy and mechanism clear and mostly reproducible.
- **Developing (6)** - Basic overview; missing pipeline or reproduction detail;
  reproducing it requires guesswork.
- **Marginal (3)** - Fragmentary, with major gaps; hard to follow.
- **None (0)** - Missing or too vague to use.

### 5. Hardware Exploitation Demonstration
- **Exemplary (10)** - On the physical board, shows *both* correct normal operation
  (the self-test) *and* the payload triggering, with clear captured evidence
  (host log, logic/scope trace, or video).
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
**2nd and 3rd** earn bonus credit here. Each additional Trojan must be
**distinct** - a different trigger *and* a different payload/mechanism, not a
variant of another - and must be documented (trigger, payload, evidence) like
the first. Each of the two additional Trojans is scored independently:

- **10** - Distinct, demonstrated triggering on the physical board, and the
  self-test still passes with it present (in its own build or a combined one).
- **5** - Works but shown only in simulation, is not clearly distinct, or
  noticeably degrades normal operation.
- **0** - Non-functional, undocumented, or a trivial duplicate of another Trojan.

### Bonus B - Key / Secret Recovery (up to 10 points)
Recovering the key, IV, or device secret provisioned into your board, documented
with the method used.
- **10** - Recovered and shown on the physical board with a clear, reproducible method.
- **5** - Credible partial recovery, or recovery shown only in simulation.
- **0** - Not attempted or not substantiated.

**Maximum:** 100 base + 20 (additional Trojans) + 10 (key recovery) = **130**.

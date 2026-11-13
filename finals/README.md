# Final Challenge
The final challenge for the CSAW AI Hardware Attack Challenge will actually consist of three challenges, each detailed below.

## Timeline
These challenges will take place over 24 hours while at CSAW. The details on the challenges will be released at 12PM EST (subject to change based on scheduling) on 12 November and must be submitted by 12PM EST (subject to change) on 13 November.


## Challenge 1 - Qualifying Trojan in Hardware
The first challenge at CSAW is to implement your Trojan from the qualifying round for the Hackster board itself and demonstrate your Trojan in hardware.

## Challenge 2 - Authenticated Encryption Cipher with EEPROM Secrets
Details on this challenge can be found in the [challenge_2 directory](./challenge_2/README.md)

## Challenge 3 - FIR Audio Filter
Details on this challenge can be found in the [challenge_3 directory](./challenge_3/README.md)

## Judging
#### Submission
There is [**one submission form for all three challenges**](https://forms.gle/QzeBjFteS9EApvzC6). Each team submits a **single `submission.zip`** by the deadline in the [Timeline](#timeline). Inside the archive, work is organized **top-level by challenge**, and within each challenge **by Trojan**. Every design is submitted both as **RTL** and as a **ready-to-run, Trojan-injected bitstream**, so judges can rebuild it *or* program a board and run it directly.

##### Archive layout
```
submission.zip
├── README.md                          (optional) team name, members, and a map of the archive
├── challenge_1/
│   ├── technical_brief.md (or .pdf)   one brief for the challenge (see below)
│   └── trojan_1/
│       ├── rtl/
│       ├── bitstream/
│       ├── tb/
│       ├── exploit/
│       └── ai/
├── challenge_2/
│   ├── technical_brief.md (or .pdf)   one brief covering every Trojan below
│   ├── trojan_1/
│   │   ├── rtl/
│   │   ├── bitstream/
│   │   ├── tb/
│   │   ├── exploit/
│   │   └── ai/
│   └── trojan_2/
│       └── …                          same layout as trojan_1
└── challenge_3/
    ├── technical_brief.md (or .pdf)
    └── trojan_1/
        └── …
```

- **Top level is one directory per challenge** (`challenge_1/`, `challenge_2/`, `challenge_3/`). Include a challenge directory only for challenges you attempted.
- **Split each challenge by Trojan.** If a challenge has more than one Trojan, put each in its own `trojan_<n>/` directory (`trojan_1/`, `trojan_2/`, …), with **`trojan_1/` as the one you want scored in the main rubric**. If a challenge has only one Trojan, you may place the `rtl/`, `bitstream/`, `tb/`, `exploit/`, and `ai/` directories directly under the challenge directory, as shown for `challenge_1/` above.
- **Each Trojan directory contains:**
  - **`rtl/`** - the AI-generated Verilog for this Trojan, synthesizable for the Hackster's iCE40-UP5K.
  - **`bitstream/`** - the **actual Trojan-injected bitstream** (`.bin`) built from that RTL, so we can program a board and run it without rebuilding. Name it clearly (e.g. `trojan_1.bin`) and say in the brief which bitstream goes with which Trojan. Each distinct Trojan's bitstream goes in its own Trojan directory; if several Trojans share one combined build, include that `.bin` and note it.
  - **`tb/`** - the simulation testbench, including the normal-operation check where one applies (`fpga_selftest.py` for Challenge 2, the baseline comparison for Challenge 3).
  - **`exploit/`** - the exploit demonstration: the host-side scripts that drive the board and activate the trigger (plus any input files they need), together with the captured evidence that it worked on the physical board - host logs, logic-analyzer/scope traces, Challenge 3 input/output audio or spectrograms, and/or a short video - and evidence that normal operation is preserved.
  - **`ai/`** - comprehensive logs (or a document linking to chat histories) of every prompt and AI response used to generate this Trojan and its exploit. **Submissions missing these logs will be disqualified.**

##### Technical brief
Each challenge directory has **one technical brief** (`technical_brief.md` or `.pdf`) that covers **all** of that challenge's Trojans. It should include:
- how the team reverse-engineered and understood the design from the bitstream - for Challenge 1, what had to change to run the qualifying Trojan on the Hackster; for Challenge 2, the accelerator and its EEPROM key-loading path; for Challenge 3, the filter response/coefficients and the I2S streaming interface;
- the AI method and model(s) used - the interaction method (API, web UI, etc.) and any framework or agentic workflow (this is largely what we judge for creative AI use);
- for **each** Trojan: its trigger, payload, stealth measures, **which bitstream in `bitstream/` it corresponds to**, and a reproducible description with enough detail to reproduce it on a board from the RTL;
- which Trojan is the team's strongest (scored in that challenge's main rubric);
- any bonus claims (additional Trojans, Challenge 2 key/secret recovery, Challenge 3 covert channel).

Each challenge's scoring rubric remains in its own README. As in the qualifying round, documentation and AI logs are required.

#### Presentation
Each team must present its solutions to all three challenges to our panel of judges. The presentation must detail how the team used generative AI, the specific strategy taken for each problem, and any challenges faced along the way.

Presentations are worth a total of **20 points**, scored with the [rubric below](#presentation-rubric). These points are in addition to the points from each challenge's own scoring rubric.

##### Format
- **One slot per team, covering all three challenges.** Each team gets a single **10-minute** slot for its presentation and judge questions combined. We recommend about **7 minutes of presentation**, leaving about **3 minutes for judge questions**.
- **Time is enforced.** The slot ends at 10 minutes. Any time you present past 7 minutes comes out of your question time, and how you handle questions is part of your score.
- **Presenters.** Any or all team members may present. Every team member should be ready to answer questions about the team's work.
- **Slides.** *(organizer: state whether teams present from their own laptops or submit slides in advance, the slide deadline if any, and the display connection available.)*
- **Schedule.** *(organizer: insert the presentation schedule and room.)*

**You do not need to demo each exploit during your presentation. We will be running your Trojan-infected hardware and running your exploit scripts on it ourselves.** Screenshots, short clips, scope or logic-analyzer captures, and spectrograms of your hardware results are welcome on your slides, but a live demo is not expected.

##### What to Cover
Presentations should cover the following topics:

1. **How you used generative AI.** This is the headline of your talk: sell us on your creative generative AI use.
   - The model(s) and interfaces you used (API, web UI, IDE agent, etc.), and any framework, agentic workflow, or scripts you built around them.
   - Where AI was used across the whole flow: reverse-engineering the bitstreams, understanding the designs, generating and inserting the Trojans, writing exploit and test scripts, and debugging on hardware.
   - What was automated end to end, and where a human had to step in.
   - At least one concrete example, such as a prompt and the result it produced or a step of your pipeline, not only a description.
   - Where the AI fell short and how you worked around it.

2. **What each Trojan does.** For each challenge:
   - **Challenge 1:** your qualifying-round Trojan, and what had to change to run it on the Hackster (pinout, clocking, resource limits, real I/O).
   - **Challenge 2:** how you recovered the accelerator and its EEPROM key-loading path from the bitstream, then the trigger, payload, and stealth measures of each Trojan.
   - **Challenge 3:** how you recovered the filter and its I2S streaming interface from the bitstream, then the trigger, payload, and stealth measures of each Trojan.
   - Why you chose that trigger and payload for that target, and anything you are claiming for bonus credit (additional Trojans, key recovery, covert channel).

3. **How your exploit demo works.** Judges will run your exploits themselves, so tell us what to expect:
   - What the exploit script sends to the board, step by step, and how that activates the trigger.
   - What a judge should see when the Trojan fires, and how it differs from normal operation.
   - How you showed that normal operation is preserved (`fpga_selftest.py` for Challenge 2, the baseline check for Challenge 3).
   - Any setup the judges need: board state, file names, ports, and the order to run scripts in.

4. **Challenges faced.** The biggest obstacles you hit (reverse-engineering, hardware bring-up, timing, AI failures) and what you did about them. These can be woven into the sections above rather than given their own slide.

If your team did not finish a challenge, still present what you attempted and where you got stuck.

##### Suggested Structure
This is a guide, not a requirement.

| Segment | Time |
| :--- | :---: |
| Generative AI approach and pipeline | ~2 min |
| Challenge 1: Trojan and exploit | ~1 min |
| Challenge 2: Trojan(s) and exploit | ~1.5 min |
| Challenge 3: Trojan(s) and exploit | ~1.5 min |
| Challenges faced and wrap-up | ~1 min |
| Judge questions | ~3 min |

#### Presentation Rubric
Each category is scored at **one of five fixed levels**: judges pick the column that best fits and record its points. As in the challenge rubrics, generative AI use carries the most weight.

| Category | Exemplary | Strong | Proficient | Developing | None |
| :--- | :---: | :---: | :---: | :---: | :---: |
| 1. Generative AI Use | 8 | 6 | 4 | 2 | 0 |
| 2. Trojan Design & Strategy | 4 | 3 | 2 | 1 | 0 |
| 3. Exploit Explanation | 4 | 3 | 2 | 1 | 0 |
| 4. Delivery & Q&A | 4 | 3 | 2 | 1 | 0 |
| **Total** | **20** | | | | |

##### 1. Generative AI Use
- **Exemplary (8)** - A clear, compelling account of a creative AI workflow across all three challenges, backed by concrete examples (prompts, pipeline steps, agent loops). Candid about where the AI fell short and how the team adapted.
- **Strong (6)** - A clear workflow with concrete examples; creative in places, or one challenge is covered thinly.
- **Proficient (4)** - Names the models and tools and roughly how they were used, but mostly at a high level with few concrete examples.
- **Developing (2)** - Vague or generic ("we asked the AI to write it"); hard to tell what the AI actually did.
- **None (0)** - AI use not covered.

##### 2. Trojan Design & Strategy
- **Exemplary (4)** - Trigger, payload, and stealth explained clearly for every Trojan across all three challenges, with the reasoning behind each choice and the reverse-engineering approach for Challenges 2 and 3.
- **Strong (3)** - All Trojans explained clearly; the reasoning or reverse-engineering approach is thin for one challenge.
- **Proficient (2)** - Trojans described, but one challenge is missing or the explanations are hard to follow.
- **Developing (1)** - Only a partial or superficial description of the Trojans.
- **None (0)** - Trojans not explained.

##### 3. Exploit Explanation
- **Exemplary (4)** - For each challenge, judges know how the exploit activates the Trojan, what they will see when it fires, and how normal operation was shown to be preserved.
- **Strong (3)** - Clear for most challenges; minor gaps in the expected output or the normal-operation evidence.
- **Proficient (2)** - Exploit flow described, but judges would need the written brief to know what to run or expect.
- **Developing (1)** - Exploits mentioned with little explanation of how they work.
- **None (0)** - Exploits not covered.

##### 4. Delivery & Q&A
- **Exemplary (4)** - Well organized and on time, leaving room for questions. Answers are accurate and direct and show the team understands its own designs, not just the AI's output.
- **Strong (3)** - Clear and close to time; answers are mostly solid.
- **Proficient (2)** - Understandable but disorganized, or runs long enough to cut questions short; some answers are vague.
- **Developing (1)** - Hard to follow, or uses up most of the question time; the team struggles to answer questions about its own work.
- **None (0)** - No presentation given.

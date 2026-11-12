# Hackster iCE40 Authenticated Crypto IP Core

## Introduction
This IP core implements a lightweight **authenticated encryption** accelerator
for the Lattice iCE40 UltraPlus FPGA on the Hackster board. It encrypts or
decrypts a variable-length message and, unlike a bare block transform, also
produces and verifies a 128-bit **authentication tag**, so tampered input is
rejected rather than silently decrypted.

The core's key material is **not** contained in the FPGA bitstream. A key, an
initialization vector (nonce), and an additional device secret are provisioned
into an on-board I2C EEPROM, and the core loads them itself shortly after
configuration. To keep a minimal resource footprint, the core exposes a raw SPI
peripheral interface with a small command protocol rather than a full bus
interface (AXI/Wishbone).

## 2. IP Core Overview

The application processor (RP2040) is the **SPI Controller**; the FPGA is the
**SPI Peripheral**. The controller issues single-byte commands over SPI to load
input data into internal buffers, start an operation, poll status, and read the
result (ciphertext/plaintext and tag) back.

**Clocking note.** Unlike a purely SCK-driven design, this core runs on a
free-running system clock (`ICE_CLK`, nominally 10 MHz, supplied by the
programmer). The SPI interface is *oversampled* against that clock, so the SPI
clock (`SCK`) must not exceed **1 MHz**. SPI is mode 0 (CPOL=0, CPHA=0),
MSB-first.

**Key loading.** After configuration the core automatically reads the EEPROM
(I2C), validates the stored image, and latches the key, nonce, and secret into
internal registers. These values are held inside the FPGA and are **never**
exposed through the SPI command interface. A status bit reports when key loading
has completed successfully.

## 3. Port Descriptions

| Pin Name | Direction | Description |
| --- | --- | --- |
| `ICE_CLK` | Input | Free-running system clock (~10 MHz) from the programmer. Drives the whole core. |
| `SPI_SCK` | Input | SPI clock from the controller (**max 1 MHz**); oversampled internally. |
| `SPI_CS_N` | Input | Active-low SPI chip-select / frame delimiter. Each command is one CS-low..CS-high frame. |
| `SPI_MOSI` | Input | SPI Controller Out, Peripheral In (serial data). |
| `SPI_MISO` | Output | SPI Controller In, Peripheral Out (serial data). |
| `BUSY` | Output | Status flag. High while the crypto engine is processing an operation. |
| `PERIPH_SDA` | Bidir | I2C data to the on-board key EEPROM (and shared peripheral bus). |
| `PERIPH_SCL` | Output | I2C clock to the on-board key EEPROM. |
| `ICE_LED` | Output | Activity indicator, high while the engine is processing (also routed to the scope-trigger SMA). |
| `RGB_R/G/B` | Output | Status LEDs (active-low): key-loaded, error, and activity indications. |

Header / application-processor mapping for the SPI signals:

| Signal | FPGA pin | Header | RP2040 (AppMicro) |
| --- | ---: | :---: | --- |
| `SPI_MISO` | 32 | D2 | GPIO8 (SPI1 RX) |
| `SPI_CS_N` | 31 | D3 | GPIO9 (GPIO) |
| `SPI_SCK` | 28 | D4 | GPIO10 (SPI1 SCK) |
| `SPI_MOSI` | 26 | D5 | GPIO11 (SPI1 TX) |
| `BUSY` | 23 | D8 | GPIO14 |
| `PERIPH_SDA` / `PERIPH_SCL` | 4 / 3 | - | on-board EEPROM (I2C `0x50`) |

## 4. SPI Command Protocol

Every SPI frame (CS low → CS high) begins with a **command byte**. While that
byte is shifted in, the core shifts the current **status byte** out on `MISO`.

| Command | Frame (controller → peripheral) | Effect |
| --- | --- | --- |
| `0x00` NOP / STATUS | `00` | Return the status byte only. |
| `0x01` WRITE | `01 AH AL d0 d1 …` | Write data bytes into the input buffer starting at 16-bit address `AH:AL`. |
| `0x02` READ | `02 AH AL 00` + N bytes | Read N buffer bytes from address `AH:AL` (one dummy byte precedes the data). |
| `0x03` START | `03 CFG ADL ADH MSL MSH` | Begin an operation when CS is deasserted. |
| `0x04` LOAD_KEYS | `04` | Re-read and re-validate the EEPROM key image. |
| `0x05` INFO | `05` + 7 bytes | Return status, key-load code, a version byte, and a 4-byte identification signature. |
| `0x06` RESET | `06` | Reset the crypto engine (loaded key material is retained). |

**Buffer map** (16-bit addresses used by WRITE/READ):

| Address | Region | Access | Purpose |
| --- | --- | --- | --- |
| `0x000` | AD | R/W | Associated data (up to 512 B) |
| `0x200` | MSG | R/W | Plaintext to encrypt / ciphertext to decrypt (up to 512 B) |
| `0x400` | OUT | R | Result (ciphertext or recovered plaintext) |
| `0x600` | TAG_IN | R/W | Tag to verify on decryption |
| `0x610` | TAG_OUT | R | Tag produced on encryption |
| `0x620` | NONCE_IN | R/W | Host-supplied nonce |

Buffer accesses are ignored while `BUSY` is high.

**START configuration byte (`CFG`):**
- bits `[1:0]` - operation: `1` encrypt, `2` decrypt, `3` encrypt the device secret.
- bits `[3:2]` - nonce source: `0` EEPROM nonce, `1` host `NONCE_IN`, `2` EEPROM nonce XOR host `NONCE_IN`.
- `ADL:ADH` and `MSL:MSH` give the associated-data and message lengths in bytes.

**Status byte (returned during every command byte):**

| Bit | Name | Meaning |
| --- | --- | --- |
| 0 | BUSY | Engine is processing. |
| 1 | DONE | Last operation completed. |
| 2 | AUTH_OK | Last decryption's tag verified. |
| 3 | AUTH_FAIL | Last decryption's tag did not verify. |
| 4 | KEYS_LOADED | Key material loaded from EEPROM and valid. |
| 5 | EEPROM_ERROR | EEPROM read/validation error. |
| 6 | COMMAND_ERROR | Last START rejected (no keys, or bad parameters). |
| 7 | (reserved, always 1) | Liveness marker; `0x00`/`0xFF` means no peripheral is responding. |

**Key-load codes (INFO byte 2):** `0x00` ok, `0x01` EEPROM no-ACK, `0x02` bad
magic (not provisioned), `0x03` bad version, `0x04` CRC mismatch, `0x05` I2C bus
stuck, `0xFE` loading, `0xFF` not yet read.

## 5. EEPROM Key-Image Format

The key material is provisioned into the on-board EEPROM (I2C address `0x50`) as
a 64-byte image beginning at word address `0x00`. The core validates this image
before use.

| Offset | Size | Contents |
| --- | --- | --- |
| `0x00` | 4 | Magic signature |
| `0x04` | 1 | Image version (`0x01`) |
| `0x05` | 9 | Reserved (zero) |
| `0x0E` | 2 | CRC-16/CCITT-FALSE of bytes `0x10`–`0x3F`, big-endian |
| `0x10` | 16 | Key |
| `0x20` | 16 | Nonce / IV |
| `0x30` | 16 | Device secret |

Because the EEPROM sits on the FPGA's peripheral bus rather than on the
application processor, provisioning is done by first loading the board's I2C
pass-through bitstream, writing the image from the application processor, and
then loading this accelerator bitstream. See the provisioning script in this
directory.

## 6. Usage Guideline

To provision, run an operation, and read the result, the application processor
should follow this sequence.

### Step 0: Provision the key material (one time)
Load the I2C pass-through bitstream, write the 64-byte key image to the EEPROM,
then load this accelerator bitstream.

### Step 1: Wait for key loading
After the accelerator bitstream is loaded, the core reads the EEPROM on its own
(within a few milliseconds of configuration). Poll `INFO`/`STATUS` until
`KEYS_LOADED` is set (key-load code `0x00`). An error code here means the EEPROM
is unprovisioned or corrupt.

### Step 2: Load inputs
Using `WRITE`, place the associated data at `0x000`, the message at `0x200`, and
- for a host or XOR nonce - 16 nonce bytes at `0x620`. For decryption, also write
the 16-byte tag to `0x600`.

### Step 3: Start the operation
Issue `START` with the desired `CFG` and the AD/message lengths. The operation
begins when `CS_N` is deasserted at the end of the frame.

### Step 4: Wait for completion
Poll `STATUS`. `BUSY` is high while the engine runs and falls when the operation
completes; `DONE` is then set. For decryption, check `AUTH_OK` / `AUTH_FAIL`.

### Step 5: Read the result
Using `READ`, read the output from `0x400` (ciphertext, or recovered plaintext)
and, for encryption, the tag from `0x610`. On a failed tag verification the
output is withheld (reads back as zeros).

---

> **Organizer note (remove before public release).** This document intentionally
> does not name the underlying algorithm, matching the qualifier's IP doc. Note
> that the `INFO` identification signature and the EEPROM magic currently spell a
> hint toward the cipher; rename them in the RTL/bitstream if you want to
> preserve that part of the reverse-engineering challenge. The full reference
> design (algorithm, datapath, and block diagrams) is the answer key and should
> stay out of this provided directory.

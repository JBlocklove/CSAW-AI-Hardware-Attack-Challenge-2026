#!/usr/bin/env python3
"""Stream a WAV file through the audio filter on the Hackster's FPGA.

  python3 stream_audio.py noisy.wav filtered.wav --port /dev/ttyACM1
  python3 stream_audio.py --self-test --port /dev/ttyACM1

The audio goes from this PC over USB to the RP2040 application processor,
which passes it to the FPGA over I2S and sends the FPGA's output back. Nothing
is stored on the board, so files can be any length.

At the start of every run this script sends audio_bridge.py (kept in the same
folder as this script) to the RP2040 through MicroPython's raw REPL, the same
way `mpremote run` works, so nothing has to be copied to the board. The board
only needs the MicroPython firmware. Close Thonny and any mpremote session
first: only one program can hold the serial port.

The input must be a 16-bit mono PCM WAV; the output has the same length and
sample rate. To convert another recording, for example with ffmpeg:
  ffmpeg -i input.wav -ac 1 -ar 16000 -sample_fmt s16 output.wav

Each frame the FPGA returns also carries an echo of the sample it received
(see the FPGA interface documentation). This script checks every echo, so a
bad I2S link is always reported. --self-test checks only the link: it sends
test samples and confirms that all of them come back intact.

Ctrl-C stops after the current chunk and keeps what was processed so far.
Needs pyserial: python3 -m pip install -r requirements.txt
"""
import argparse
import os
import random
import signal
import struct
import sys
import time
import wave
from array import array

try:
    import serial
except ImportError:
    sys.exit("needs pyserial: python3 -m pip install -r requirements.txt")

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "audio_bridge.py")

CHUNK = 1024          # frames per request; must not exceed CHUNK in audio_bridge.py
LATENCY = 2           # the reply to frame n arrives in frame n + 2 (interface doc)
FLUSH = 1024          # zero frames sent first, so no audio from an earlier run leaks in
NOMINAL_RATE = 16000  # nominal audio rate (interface doc)
MAX_RATE = 31250      # fastest I2S frame rate the FPGA accepts (BCLK 1 MHz)
READY = b"AUDIO-BRIDGE-READY\n"
RAW_BANNER = b"raw REPL; CTRL-B to exit\r\n"
DEFAULT_PORT = os.environ.get("HACKSTER_APP_PORT", "/dev/ttyACM1")


class BoardError(Exception):
    pass


class Bridge:
    """The RP2040 running audio_bridge.py, reached over its USB serial port."""

    def __init__(self, port):
        try:
            self.ser = serial.Serial(port, 115200, timeout=0.1, write_timeout=5)
        except serial.SerialException as e:
            raise BoardError("cannot open %s (%s).\nIs it the application processor's "
                             "port, and are Thonny and mpremote closed?" % (port, e))
        self.port = port
        self.rate = None
        self.link_errors = 0

    # ---- low-level reads ----
    def read_exact(self, n, timeout):
        buf = b""
        deadline = time.monotonic() + timeout
        while len(buf) < n:
            buf += self.ser.read(n - len(buf))
            if len(buf) < n and time.monotonic() > deadline:
                raise BoardError("timed out waiting for the board (got %d of %d bytes)"
                                 % (len(buf), n))
        return buf

    def read_until(self, marker, timeout):
        buf = b""
        deadline = time.monotonic() + timeout
        while not buf.endswith(marker):
            c = self.ser.read(1)
            buf += c
            if not c and time.monotonic() > deadline:
                raise BoardError("timed out waiting for %r from the board" % marker)
        return buf

    def board_error(self, got):
        """Something other than a reply came back: usually a Python traceback."""
        try:
            text = got + self.read_until(b"\x04>", 2)
        except BoardError:
            text = got + self.ser.read(4096)
        text = text.replace(b"\x04", b"").rstrip(b">").decode(errors="replace").strip()
        return BoardError("the board stopped with:\n" + text)

    # ---- raw REPL: how mpremote runs code ----
    def start(self, rate):
        """Soft-reset the RP2040, send audio_bridge.py and start serve(rate)."""
        try:
            with open(BRIDGE, "rb") as f:
                code = f.read()
        except OSError:
            raise BoardError("cannot read %s: keep audio_bridge.py in the same folder "
                             "as this script" % BRIDGE)
        for _ in range(5):
            self.ser.write(b"\r\x03\x03")          # Ctrl-C: stop whatever is running
            time.sleep(0.1)
            self.ser.reset_input_buffer()
            self.ser.write(b"\r\x01")              # Ctrl-A: raw REPL
            try:
                self.read_until(RAW_BANNER + b">", 1.0)
                break
            except BoardError:
                pass
        else:
            raise BoardError("no MicroPython prompt on %s.\nIs this the application "
                             "processor's port (not the programmer), with MicroPython "
                             "installed? If an earlier run was killed mid-transfer, press "
                             "the application processor's RESET button." % self.port)
        self.ser.write(b"\x04")                    # Ctrl-D: soft reset (frees PIO and DMA)
        self.read_until(b"soft reboot\r\n", 5)
        self.read_until(RAW_BANNER + b">", 5)

        code += b"\nserve(%d, %d)\n" % (rate, CHUNK)
        self.ser.write(code + b"\x04")             # Ctrl-D: run it
        if self.read_exact(2, 5) != b"OK":
            raise BoardError("the board did not accept the bridge code")
        got = b""
        deadline = time.monotonic() + 10
        while not got.endswith(READY):
            c = self.ser.read(1)
            if c == b"\x04":                       # finished before READY: an error
                raise self.board_error(b"")
            got += c
            if time.monotonic() > deadline:
                raise BoardError("the bridge did not start; the board printed:\n%s"
                                 % got.decode(errors="replace"))
        self.rate = rate

    def finish(self):
        """End the stream and leave the RP2040 at its normal prompt."""
        self.ser.write(b"FR\x00\x00")
        got = self.read_exact(4, 5)
        if got != b"fr\x00\x00":
            raise self.board_error(got)
        tail = self.read_until(b"\x04>", 5)        # stdout \x04 stderr \x04 >
        err = tail.split(b"\x04")[1] if tail.count(b"\x04") >= 2 else b""
        self.ser.write(b"\x02")                    # Ctrl-B: back to the normal REPL
        if err.strip():
            raise BoardError("the board reported:\n" + err.decode(errors="replace"))

    def close(self):
        self.ser.close()

    # ---- one request, one reply ----
    def exchange(self, samples):
        """Send one I2S frame per sample (left = right = the sample). Return the
        FPGA's replies as (left, right) pairs of signed 16-bit values."""
        n = len(samples)
        words = [(s & 0xFFFF) * 0x10001 for s in samples]
        self.ser.write(struct.pack("<2sH%dI" % n, b"FR", n, *words))
        head = self.read_exact(4, 5)
        if head != b"fr" + struct.pack("<H", n):
            raise self.board_error(head)
        data = self.read_exact(4 * n, 5 + 4 * n / self.rate)
        return [((((w >> 16) ^ 0x8000) - 0x8000), ((w & 0xFFFF) ^ 0x8000) - 0x8000)
                for w in struct.unpack("<%dI" % n, data)]


def process_stream(bridge, blocks, stop=lambda: False):
    """Stream blocks of int16 samples through the FPGA; yield output blocks.

    Output sample k is the FPGA's output (left channel) for input sample k, so
    the output has exactly as many samples as the input. The right-channel echo
    of every frame is checked against the sample that was sent."""
    def frames():                      # (sample, is_real) for every frame sent
        for _ in range(FLUSH):
            yield 0, False
        for block in blocks:
            for s in block:
                yield s, True
            if stop():
                break
        for _ in range(LATENCY):       # two more frames bring back the last replies
            yield 0, False

    def requests():
        batch = []
        for fr in frames():
            batch.append(fr)
            if len(batch) == CHUNK:
                yield batch
                batch = []
        if batch:
            yield batch

    earlier = [None] * LATENCY         # frames sent before this run: replies not checked
    for batch in requests():
        replies = bridge.exchange([s for s, _ in batch])
        in_flight = earlier + batch    # in_flight[i] is the frame that reply i answers
        out = []
        for (y, echo), fr in zip(replies, in_flight):
            if fr is None:
                continue
            s, real = fr
            if echo != s:
                bridge.link_errors += 1
            if real:
                out.append(y)
        earlier = in_flight[-LATENCY:]
        yield out


# ---------------------------------------------------------------------------
def to_bytes(samples):
    a = array("h", samples)
    if sys.byteorder == "big":
        a.byteswap()
    return a.tobytes()


def from_bytes(data):
    a = array("h")
    a.frombytes(data)
    if sys.byteorder == "big":
        a.byteswap()
    return a.tolist()


def report_link(bridge, n):
    if bridge.link_errors == 0:
        print("link check: OK, all %d samples came back intact" % n)
        return True
    print("link check: %d of %d samples came back wrong." % (bridge.link_errors, n))
    if bridge.link_errors > n // 2:
        print("Nothing sensible came back: is the bitstream loaded on the FPGA?")
    return False


def run_file(bridge, src, dst, rate_arg):
    try:
        wi = wave.open(src, "rb")
    except (OSError, wave.Error) as e:
        raise SystemExit("%s: %s" % (src, e))
    with wi:
        if wi.getnchannels() != 1 or wi.getsampwidth() != 2:
            raise SystemExit("%s: need a 16-bit mono PCM WAV. To convert:\n"
                             "  ffmpeg -i %s -ac 1 -ar 16000 -sample_fmt s16 out.wav"
                             % (src, src))
        fs, total = wi.getframerate(), wi.getnframes()
        if fs != NOMINAL_RATE:
            print("warning: %s is %d Hz; the filter expects %d Hz audio"
                  % (src, fs, NOMINAL_RATE))
        rate = rate_arg or min(fs, MAX_RATE)
        if not 2000 <= rate <= MAX_RATE:
            raise SystemExit("I2S rate must be 2000..%d frames/s (use --rate)" % MAX_RATE)

        stopped = []
        old = signal.signal(signal.SIGINT, lambda *a: stopped.append(1))

        def blocks():
            while True:
                data = wi.readframes(CHUNK)
                if not data:
                    return
                yield from_bytes(data)

        print("streaming %s (%.2f s at %d Hz) over %s, I2S at %d frames/s ..."
              % (src, total / fs, fs, bridge.port, rate))
        done, t0, last = 0, time.monotonic(), 0.0
        try:
            bridge.start(rate)
            with wave.open(dst, "wb") as wo:
                wo.setnchannels(1)
                wo.setsampwidth(2)
                wo.setframerate(fs)
                for out in process_stream(bridge, blocks(), stop=lambda: bool(stopped)):
                    wo.writeframes(to_bytes(out))
                    done += len(out)
                    now = time.monotonic()
                    if now - last > 0.5 or done == total:
                        last = now
                        print("\r  %6.1f s of %.1f s" % (done / fs, total / fs),
                              end="", file=sys.stderr, flush=True)
            bridge.finish()
        finally:
            signal.signal(signal.SIGINT, old)
            print(file=sys.stderr)
    dt = time.monotonic() - t0
    print("wrote %s: %d samples in %.1f s%s"
          % (dst, done, dt, ", stopped early" if stopped else ""))
    return report_link(bridge, done)


def run_self_test(bridge, rate):
    """Check the I2S link only: every sample must come back on the echo channel."""
    rng = random.Random(2026)
    x = [-32768, 32767, 0, -1, 1, 0x5555, -0x5556] * 8      # extreme and alternating bits
    x += [rng.randint(-32768, 32767) for _ in range(4000)]
    print("self-test: sending %d samples and checking the echo channel" % len(x))
    bridge.start(rate)
    n = 0
    for out in process_stream(bridge, [x]):
        n += len(out)
    bridge.finish()
    ok = report_link(bridge, len(x)) and n == len(x)
    if n != len(x):
        print("expected %d output samples, got %d" % (len(x), n))
    print("PASS" if ok else "FAIL")
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="?", help="16-bit mono WAV to process")
    p.add_argument("output", nargs="?", help="where to write the output WAV")
    p.add_argument("--port", default=DEFAULT_PORT,
                   help="application processor serial port (default %(default)s; "
                        "or set HACKSTER_APP_PORT)")
    p.add_argument("--rate", type=int, default=0,
                   help="I2S frames per second, up to %d (default: the file's sample "
                        "rate). It does not change the result; faster finishes sooner."
                   % MAX_RATE)
    p.add_argument("--self-test", action="store_true",
                   help="check the I2S link: every sample must come back intact")
    args = p.parse_args()
    if not args.self_test and not (args.input and args.output):
        p.error("give an input and an output WAV, or --self-test")

    bridge = Bridge(args.port)
    try:
        if args.self_test:
            ok = run_self_test(bridge, args.rate or NOMINAL_RATE)
        else:
            ok = run_file(bridge, args.input, args.output, args.rate)
    except BoardError as e:
        sys.exit("error: %s" % e)
    finally:
        bridge.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

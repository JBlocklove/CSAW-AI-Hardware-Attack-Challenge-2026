# audio_bridge.py - USB-to-I2S bridge for the Hackster's application processor (RP2040).
#
# You do not need to copy this file to the board: stream_audio.py on the PC
# sends it over USB at the start of every run (through MicroPython's raw REPL)
# and then calls serve().
#
# The PC streams I2S frames over the USB serial port; this code sends them to
# the FPGA over I2S and sends the FPGA's replies straight back. It does no
# audio processing and stores nothing: one chunk at a time, in RAM.
#
# Protocol (little-endian), one request then one reply, repeated:
#   PC -> board    b"FR" + uint16 n + n x uint32 frame words    (n = 1..CHUNK)
#   board -> PC    b"fr" + uint16 n + n x uint32 reply words
#   PC -> board    b"FR" + uint16 0                             end of stream
#   board -> PC    b"fr" + uint16 0
# Before the first request the board prints b"AUDIO-BRIDGE-READY\n".
#
# A frame word is (left << 16) | right, 16 bits each. See the FPGA interface
# documentation for what the FPGA returns on each channel.
#
#   AppMicro GPIO  header  FPGA pin  signal
#   GPIO6          D0      36        I2S_BCLK (bit clock)
#   GPIO7          D1      34        I2S_WS   (must be BCLK + 1: both are side-set pins)
#   GPIO8          D2      32        I2S_SD_IN  (data to the FPGA)
#   GPIO9          D3      31        I2S_SD_OUT (data from the FPGA)

import select
import sys
import time

import micropython
import rp2
from machine import Pin

PIN_BCLK = 6        # WS is PIN_BCLK + 1
PIN_TO_FPGA = 8
PIN_FROM_FPGA = 9

CHUNK = 1024        # max frames per request (4 KB each way)
MAX_RATE = 31250    # BCLK = 32 x rate; the FPGA samples BCLK at 10 MHz, so keep it <= 1 MHz


# ---------------------------------------------------------------------------
# PIO program: full-duplex I2S controller, 16-bit stereo, Philips format.
#
# Side-set bit 0 = BCLK, bit 1 = WS. Each bit takes 4 PIO clocks: BCLK low for
# 2 (the "out" and its [1] delay) and high for 2 (the "in" and the jmp/set).
# So the PIO clock is 4 x 32 x rate = 128 x rate.
#
# A frame is 32 bits: L15..L0 then R15..R0. WS changes one bit early (it goes
# high with L0 and low with R0), which is why L0 and R0 have their own code.
# With autopull/autopush at 32 bits, each TX word is one frame out and each RX
# word is one frame in. When the TX FIFO runs dry, "out" stalls at the start
# of a frame with BCLK low, so the link simply pauses between chunks.
# ---------------------------------------------------------------------------
@rp2.asm_pio(
    sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW),
    out_init=rp2.PIO.OUT_LOW,
    out_shiftdir=rp2.PIO.SHIFT_LEFT,     # MSB first
    in_shiftdir=rp2.PIO.SHIFT_LEFT,
    autopull=True,
    pull_thresh=32,
    autopush=True,
    push_thresh=32,
)
def i2s_duplex():
    set(x, 14)              .side(0b00)
    wrap_target()
    label("left")                         # L15..L1, WS low
    out(pins, 1)            .side(0b00) [1]
    in_(pins, 1)            .side(0b01)
    jmp(x_dec, "left")      .side(0b01)
    out(pins, 1)            .side(0b10) [1]   # L0, WS goes high
    in_(pins, 1)            .side(0b11)
    set(x, 14)              .side(0b11)
    label("right")                        # R15..R1, WS high
    out(pins, 1)            .side(0b10) [1]
    in_(pins, 1)            .side(0b11)
    jmp(x_dec, "right")     .side(0b11)
    out(pins, 1)            .side(0b00) [1]   # R0, WS goes low
    in_(pins, 1)            .side(0b01)
    set(x, 14)              .side(0b01)
    wrap()


class I2SLink:
    """The I2S link to the FPGA: one PIO state machine and two DMA channels."""

    def __init__(self, rate=16000, chunk=CHUNK, sm_id=0):
        if not 2000 <= rate <= MAX_RATE:
            raise ValueError("rate must be 2000..%d Hz" % MAX_RATE)
        self.rate = rate
        Pin(PIN_FROM_FPGA, Pin.IN)
        self.sm = rp2.StateMachine(
            sm_id, i2s_duplex, freq=128 * rate,
            sideset_base=Pin(PIN_BCLK), out_base=Pin(PIN_TO_FPGA),
            in_base=Pin(PIN_FROM_FPGA))
        # DMA request lines for this state machine (RP2040 datasheet 2.5.3.1)
        pio, n = sm_id // 4, sm_id % 4
        self.dreq_tx = pio * 8 + n
        self.dreq_rx = pio * 8 + 4 + n
        self.tx_dma = rp2.DMA()
        self.rx_dma = rp2.DMA()
        # Frame buffers, 4 bytes per frame. bytearray data lives in its own
        # heap block, so it is word-aligned as the DMA requires.
        self.tx = bytearray(4 * chunk)
        self.rx = bytearray(4 * chunk)
        self.sm.active(1)   # runs "set x" then stalls at the first "out"

    def close(self):
        self.sm.active(0)
        self.tx_dma.close()
        self.rx_dma.close()

    def transfer(self, n):
        """Send the first n frames of self.tx; the n replies land in self.rx."""
        rx_ctrl = self.rx_dma.pack_ctrl(size=2, inc_read=False, inc_write=True,
                                        treq_sel=self.dreq_rx)
        tx_ctrl = self.tx_dma.pack_ctrl(size=2, inc_read=True, inc_write=False,
                                        treq_sel=self.dreq_tx)
        self.rx_dma.config(read=self.sm, write=self.rx, count=n, ctrl=rx_ctrl, trigger=True)
        self.tx_dma.config(read=self.tx, write=self.sm, count=n, ctrl=tx_ctrl, trigger=True)
        deadline = time.ticks_add(time.ticks_ms(), 100 + 2000 * n // self.rate)
        while self.rx_dma.active():
            if time.ticks_diff(deadline, time.ticks_ms()) < 0:
                raise RuntimeError("I2S transfer timed out")


def read_exact(stream, buf):
    """Fill buf (a memoryview) completely from stream."""
    got = 0
    while got < len(buf):
        n = stream.readinto(buf[got:])
        if not n:
            raise RuntimeError("USB input closed")
        got += n


def serve(rate=16000, chunk=CHUNK, idle_ms=5000):
    """Pass frames between USB and I2S until the PC sends an empty request."""
    link = I2SLink(rate, chunk)
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    head = bytearray(4)
    tx, rx = memoryview(link.tx), memoryview(link.rx)
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    micropython.kbd_intr(-1)      # from here on, byte 0x03 is data, not Ctrl-C
    try:
        out.write(b"AUDIO-BRIDGE-READY\n")
        while True:
            if not poller.poll(idle_ms):
                raise RuntimeError("no request from the PC for %d ms" % idle_ms)
            read_exact(inp, memoryview(head))
            n = head[2] | head[3] << 8
            if head[0] != 0x46 or head[1] != 0x52 or n > chunk:   # b"FR"
                raise RuntimeError("bad request header %r" % bytes(head))
            if n:
                read_exact(inp, tx[:4 * n])
                link.transfer(n)
            head[0], head[1] = 0x66, 0x72                          # b"fr"
            out.write(head)
            if n == 0:
                return
            out.write(rx[:4 * n])
    finally:
        micropython.kbd_intr(3)
        link.close()

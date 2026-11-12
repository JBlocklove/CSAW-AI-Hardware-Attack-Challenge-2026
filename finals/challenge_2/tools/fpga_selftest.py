# fpga_selftest.py - functional self-test for the Hackster FPGA crypto accelerator.
#
# Run it to confirm your board and the accelerator bitstream are working before
# you start. It talks to the accelerator only through its SPI command interface
# (see the IP core interface documentation) and checks behaviour as a black box:
# it never reads, and cannot read, any key material held inside the FPGA.
#
# STANDALONE: nothing needs to be copied to the board.
#   mpremote:  mpremote connect /dev/ttyACM1 run fpga_selftest.py
#   Thonny:    open this file on your computer and press Run
#
# Prerequisite: the board's accelerator bitstream is loaded and the board has
# been provisioned with key material (your organizers do this ahead of time).

import machine

# ---- SPI link to the FPGA (SPI1 on the application processor) ----------------
# Mode 0, MSB first, <= 1 MHz (the accelerator oversamples SPI with its own clock).
cs = machine.Pin(9, machine.Pin.OUT, value=1)
spi = machine.SPI(1, baudrate=1_000_000, polarity=0, phase=0, bits=8,
                  firstbit=machine.SPI.MSB,
                  sck=machine.Pin(10), mosi=machine.Pin(11), miso=machine.Pin(8))

# ---- command bytes and buffer addresses (see the IP core interface doc) ------
CMD_STATUS = 0x00
CMD_WRITE = 0x01
CMD_READ = 0x02
CMD_START = 0x03

AD_BUF = 0x000       # associated data in
MSG_BUF = 0x200      # plaintext / ciphertext in
OUT_BUF = 0x400      # result out
TAG_IN = 0x600       # tag to verify (decrypt)
TAG_OUT = 0x610      # tag produced (encrypt)
NONCE_IN = 0x620     # host-supplied nonce

# status byte bits
ST_BUSY = 0x01
ST_AUTH_OK = 0x04
ST_KEYS_LOADED = 0x10
ST_ALIVE = 0x80

# START config byte = (nonce_source << 2) | operation
OP_ENCRYPT = 1
OP_DECRYPT = 2
NONCE_HOST = 1       # use the 16-byte nonce this script supplies


def transfer(data):
    # one SPI frame: CS low, exchange bytes, CS high
    rx = bytearray(len(data))
    cs.value(0)
    spi.write_readinto(bytes(data), rx)
    cs.value(1)
    return rx


def status():
    return transfer([CMD_STATUS])[0]


def wait_idle():
    for _ in range(100000):
        s = status()
        if not (s & ST_BUSY):
            return s
    raise RuntimeError("accelerator stayed busy")


def wait_for_keys():
    # The board loads its key material automatically a few ms after power-up.
    # On a running board this returns at once; it only waits right after a reset.
    for _ in range(20000):
        if status() & ST_KEYS_LOADED:
            return True
    return False     # board has no valid key material (not provisioned)


def write_buf(addr, data):
    if data:
        transfer([CMD_WRITE, addr >> 8, addr & 0xFF] + list(data))


def read_buf(addr, n):
    if n == 0:
        return b""
    rx = transfer([CMD_READ, addr >> 8, addr & 0xFF, 0] + [0] * n)
    return bytes(rx[4:])


def start(op, nonce_src, ad_len, msg_len):
    cfg = (nonce_src << 2) | op
    transfer([CMD_START, cfg, ad_len & 0xFF, ad_len >> 8, msg_len & 0xFF, msg_len >> 8])
    return wait_idle()


def encrypt(nonce, ad, msg):
    write_buf(NONCE_IN, nonce)
    write_buf(AD_BUF, ad)
    write_buf(MSG_BUF, msg)
    start(OP_ENCRYPT, NONCE_HOST, len(ad), len(msg))
    return read_buf(OUT_BUF, len(msg)), read_buf(TAG_OUT, 16)


def decrypt(nonce, ad, ct, tag):
    write_buf(NONCE_IN, nonce)
    write_buf(AD_BUF, ad)
    write_buf(MSG_BUF, ct)
    write_buf(TAG_IN, tag)
    s = start(OP_DECRYPT, NONCE_HOST, len(ad), len(ct))
    if s & ST_AUTH_OK:
        return read_buf(OUT_BUF, len(ct))
    return None     # tag did not verify


def hexs(b):
    return "".join("%02x" % x for x in b)


def check(name, ok):
    print(("  PASS " if ok else "  FAIL ") + name)
    return ok


def main():
    ok = True

    print("Link:")
    s = status()
    ok &= check("accelerator responds", s not in (0x00, 0xFF) and bool(s & ST_ALIVE))
    ok &= check("key material loaded", wait_for_keys())

    # Test inputs chosen by this script. The nonce here is a host test value, not
    # anything stored on the board.
    nonce = bytes(range(16))
    ad = b"hackster-selftest"
    msg = b"The quick brown fox jumps over the lazy dog."

    print("Encrypt / decrypt:")
    ct, tag = encrypt(nonce, ad, msg)
    print("    ciphertext:", hexs(ct))
    print("    tag:       ", hexs(tag))
    ok &= check("ciphertext length matches plaintext", len(ct) == len(msg))
    ok &= check("ciphertext differs from plaintext", ct != msg)
    ok &= check("tag is 16 bytes", len(tag) == 16)
    ok &= check("decrypt recovers the message", decrypt(nonce, ad, ct, tag) == msg)

    print("Authentication:")
    bad_ct = bytearray(ct)
    bad_ct[0] ^= 0x01
    ok &= check("modified ciphertext is rejected", decrypt(nonce, ad, bytes(bad_ct), tag) is None)
    ok &= check("rejected plaintext is withheld (reads as zeros)",
                read_buf(OUT_BUF, len(ct)) == bytes(len(ct)))
    bad_tag = bytearray(tag)
    bad_tag[0] ^= 0x01
    ok &= check("modified tag is rejected", decrypt(nonce, ad, ct, bytes(bad_tag)) is None)
    ok &= check("wrong associated data is rejected", decrypt(nonce, b"wrong-ad", ct, tag) is None)

    print("Consistency:")
    ct2, tag2 = encrypt(nonce, ad, msg)
    ok &= check("same inputs give the same output", ct2 == ct and tag2 == tag)
    empty_ct, empty_tag = encrypt(nonce, b"", b"")
    ok &= check("empty message authenticates", decrypt(nonce, b"", empty_ct, empty_tag) == b"")

    print("\nAll checks passed." if ok else "\nSOME CHECKS FAILED.")
    return ok


main()

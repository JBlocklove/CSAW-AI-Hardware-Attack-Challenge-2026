# fpga_demo.py - minimal example of driving the Hackster FPGA crypto accelerator.
#
# Encrypts a line, decrypts it back, and prints the results. Use it as a starting
# point for your own test harness. It uses only the accelerator's SPI command
# interface (see the IP core interface documentation).
#
# STANDALONE: nothing needs to be copied to the board.
#   mpremote:  mpremote connect /dev/ttyACM1 run fpga_demo.py
#   Thonny:    open this file on your computer and press Run
#
# Prerequisite: the accelerator bitstream is loaded and the board has been
# provisioned with key material ahead of time.

import machine

# SPI1 on the application processor: mode 0, MSB first, <= 1 MHz.
cs = machine.Pin(9, machine.Pin.OUT, value=1)
spi = machine.SPI(1, baudrate=1_000_000, polarity=0, phase=0, bits=8,
                  firstbit=machine.SPI.MSB,
                  sck=machine.Pin(10), mosi=machine.Pin(11), miso=machine.Pin(8))

# command bytes, buffer addresses, status bits (see the IP core interface doc)
CMD_STATUS, CMD_WRITE, CMD_READ, CMD_START = 0x00, 0x01, 0x02, 0x03
AD_BUF, MSG_BUF, OUT_BUF = 0x000, 0x200, 0x400
TAG_IN, TAG_OUT, NONCE_IN = 0x600, 0x610, 0x620
ST_BUSY, ST_AUTH_OK, ST_KEYS_LOADED = 0x01, 0x04, 0x10

# START config byte = (nonce_source << 2) | operation
OP_ENCRYPT, OP_DECRYPT = 1, 2
NONCE_HOST = 1       # use the 16-byte nonce this script supplies


def transfer(data):
    rx = bytearray(len(data))
    cs.value(0)
    spi.write_readinto(bytes(data), rx)
    cs.value(1)
    return rx


def wait_idle():
    while transfer([CMD_STATUS])[0] & ST_BUSY:
        pass
    return transfer([CMD_STATUS])[0]


def write_buf(addr, data):
    if data:
        transfer([CMD_WRITE, addr >> 8, addr & 0xFF] + list(data))


def read_buf(addr, n):
    return bytes(transfer([CMD_READ, addr >> 8, addr & 0xFF, 0] + [0] * n)[4:]) if n else b""


def start(op, ad_len, msg_len):
    cfg = (NONCE_HOST << 2) | op
    transfer([CMD_START, cfg, ad_len & 0xFF, ad_len >> 8, msg_len & 0xFF, msg_len >> 8])
    return wait_idle()


def encrypt(nonce, ad, msg):
    write_buf(NONCE_IN, nonce)
    write_buf(AD_BUF, ad)
    write_buf(MSG_BUF, msg)
    start(OP_ENCRYPT, len(ad), len(msg))
    return read_buf(OUT_BUF, len(msg)), read_buf(TAG_OUT, 16)


def decrypt(nonce, ad, ct, tag):
    write_buf(NONCE_IN, nonce)
    write_buf(AD_BUF, ad)
    write_buf(MSG_BUF, ct)
    write_buf(TAG_IN, tag)
    if start(OP_DECRYPT, len(ad), len(ct)) & ST_AUTH_OK:
        return read_buf(OUT_BUF, len(ct))
    return None     # tag did not verify


def wait_for_keys():
    # key material loads automatically a few ms after power-up
    for _ in range(20000):
        if transfer([CMD_STATUS])[0] & ST_KEYS_LOADED:
            return
    raise RuntimeError("board has no key material (not provisioned)")


def main():
    wait_for_keys()
    nonce = bytes(range(16))              # a host test nonce
    ad = b"demo-header"
    msg = b"hello from the application processor"

    ct, tag = encrypt(nonce, ad, msg)
    print("plaintext: ", msg)
    print("ciphertext:", "".join("%02x" % b for b in ct))
    print("tag:       ", "".join("%02x" % b for b in tag))
    print("decrypted: ", decrypt(nonce, ad, ct, tag))


main()

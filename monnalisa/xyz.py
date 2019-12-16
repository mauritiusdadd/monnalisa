import logging
import threading
import socket
import math
import time
import os
import zlib
import serial

F_COLORS = {
    '0': "#CD7F32",
    '1': "silver",
    '2': "#FF0800",
    '3': "#F0F8FF",
    '4': "#006A4E",
    '5': "#FF1DCE",
    '6': "#4682B4",
    '7': "#FF4F00",
    '8': "#EAE0C8",
    '9': "#B87333",
    'A': "purple",
    'B': "blue",
    'C': "#FF8C00",
    'D': "#40826D",
    'E': "#9AB973",
    'F': "gold",
    'G': "green",
    'H': "#39FF14",
    'I': "#FFFAFA",
    'J': "#FFFF33",
    'K': "black",
    'L': "violet",
    'M': "#6F2DA8",
    'N': "#9A4EAE",
    'O': "#FAFAD2",
    'P': "#7FFF6B",
    'Q': "#F2BE79",
    'R': "red",
    'S': "#CCFF00",
    'T': "#F28500",
    'U': "#5DADEC",
    'V': "#B19CD9",
    'W': "white",
    'X': "#EE82EE",
    'Y': "yellow",
    'Z': "#FFFFE6",
}


F_LENGHT = {
    '3': 120.0,
    '5': 185.0,
    '6': 240.0,
    'C': 200.0,
}


F_MATERIAL = {
    '41': "ABS",
    '46': "TPE",
    '47': "PETG",
    '50': "PLA-0",
    '51': "PLA-1",
    '54': "PLA-T",
    '56': "PVA",
}


def filamentcolor(val):
    try:
        return F_COLORS[val]
    except KeyError:
        return 'grey'


def filamentlen(val):
    try:
        return F_LENGHT[val]
    except KeyError:
        return 0


def filamentmaterial(val):
    try:
        return F_MATERIAL[val]
    except KeyError:
        return "PLA-Unk"


class GuiLogger(logging.Handler):
    def __init__(self):
        super().__init__()
        self.edit = None

    def emit(self, record):
        if self.edit:
            self.edit.append(self.format(record))
        else:
            print(self.format(record))


def socketmsg(data):
    msg = SocketPort.PACKET_START
    msg += data + b'\n'
    msg += zlib.crc32(data).to_bytes(16, 'little')
    msg += SocketPort.PACKET_END
    return msg


def _parsemsg(msg):
    if msg[-17] != 10:
        raise ValueError("Corrupted Message")
    data = msg[:-17]
    crc = int.from_bytes(msg[-16:], 'little')
    if zlib.crc32(data) != crc:
        print(crc)
        print(zlib.crc32(data))
        raise ValueError("Corrupted Message: invalid crc32")
    return data


class SocketPort():

    PACKET_START = b'<msg>'
    PACKET_END = b'</msg>'

    def __init__(self, url, timeout=1):
        super().__init__()
        info = url.split(':')
        self.addr = info[0]
        self.port = 2222
        self.is_open = False
        self._do_stop = False
        self.timeout = timeout
        self._lock = threading.Lock()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.buffer = b''
        self._rawbuff = b''
        try:
            self.port = int(info[1])
        except (IndexError, ValueError):
            pass

        logging.info("server on %s %d", self.addr, self.port)
        self.socket.connect((self.addr, self.port))
        self.socket.settimeout(timeout)
        self.is_open = True

    def __del__(self):
        self.close()

    def readline(self):
        stme = time.time()
        while b'\n' not in self.buffer:
            self.run()
            if time.time() - stme >= self.timeout:
                return ''

        line_start = self.buffer.find(b'\n')
        line = self.buffer[:line_start]
        self.buffer = self.buffer[line_start+1:]
        return line

    def run(self):
        self._rawbuff = b''
        try:
            self._rawbuff += self.socket.recv(1024)
        except (socket.timeout, OSError):
            pass

        msg_start = self._rawbuff.find(self.PACKET_START)
        while msg_start >= 0:
            msg_start += len(self.PACKET_START)
            msg_end = self._rawbuff.find(self.PACKET_END, msg_start+1)
            if msg_end < 0:
                return

            self.buffer += _parsemsg(self._rawbuff[msg_start:msg_end])
            self._rawbuff = self._rawbuff[msg_end+len(self.PACKET_END):]
            msg_start = self._rawbuff.find(self.PACKET_START)

    def write(self, data):
        if not self.socket or not self.is_open:
            return False
        self._lock.acquire()
        if self.socket and self.is_open:
            try:
                self.socket.sendall(socketmsg(data))
            except BrokenPipeError:
                self._do_stop = True
        self._lock.release()

    def close(self):
        self.is_open = False
        self.socket.close()


class XYZPrinter(threading.Thread):
    """
    Abstraction layer that communicates with printer hardware
    """

    ACTIONS = [
        'home', 'load', 'unload', 'calibrate', 'upload', 'image'
    ]

    def __init__(self):
        super().__init__()
        self.port = None
        self._do_stop = False
        self._stopped = False
        self._upload = None
        self.block_size = None
        self.autoleveling = None
        self._print_status = None
        self.start()

    def stop(self):
        self._do_stop = True
        self.disconnect()
        # self.join()

    def connect(self, port, baud=9600, **args) -> bool:
        try:
            logging.info(f"Conneting to %s@%d...", port, baud)
            if os.path.exists(port):
                self.port = serial.Serial(port, baud, **args)
            else:
                self.port = SocketPort(port, **args)
        except (
            serial.SerialException, socket.gaierror,
            ConnectionRefusedError
        ) as exc:
            logging.error("Connetion failed on %s: %s", port, exc)
            self.port = None
            return False
        logging.info("Connected")

        self._print_status = 'ready'
        return True

    def disconnect(self):
        if self.port:
            self.port.close()

    def getprintstatus(self):
        return self._print_status if self._print_status else 'ready'

    def query(self, stat='a'):
        self.sendaction('a', func='query')

    def print(self, val):
        self.sendaction(f'print[{val}]', func='config')

    def sendFile(self, fname):
        self._upload = fname

    def sendaction(self, action, arg=None, func='action'):
        msg = f'XYZv3/{func}'
        if action:
            msg += f'={action}'
            if arg:
                msg += f':{arg}'
        if self.port and self.port.is_open:
            logging.debug("sending message: %s", msg)
            self.port.write(msg.encode())

    def message_callback(self, msg):
        # not implemented, please override
        logging.debug("printer send: %s", msg)

    def _ack(self):
        return self.port.readline().strip() == b'ok'

    def run(self):
        self.stoped = False
        retry = 0
        while not self._do_stop:
            if self.port and self.port.is_open:
                res = self.port.readline()
                if res:
                    logging.debug(res)
                    self.message_callback(res)
                elif self._upload:
                    try:
                        with open(self._upload, 'rb') as f:
                            fdata = f.read()
                    except OSError as exc:
                        logging.error("Cannot print file %s: %s",
                                      self._upload, exc)
                        self._upload = None
                        continue
                    else:
                        flen = len(fdata)
                    tosd = ''  # ',SaveToSD'
                    self.sendaction(f'sample.3w,{flen}{tosd}', func='upload')
                    time.sleep(0.1)
                    if not self._ack():
                        logging.error('Printing FAILED: initialization error')
                        if retry == 0:
                            logging.info('Retring...')

                        if retry < 3:
                            retry += 1
                            logging.info(f'New attempt: {retry}')
                            time.sleep(1)
                        else:
                            retry = 0
                            self._upload = None
                        continue
                    else:
                        self.message_callback(b'upload:{"stat":"start"}')

                    block_size = self.block_size if self.block_size else 8192
                    total_blocks = math.ceil(flen/block_size)
                    for i in range(total_blocks):
                        data = fdata[i*block_size:(i+1)*block_size]
                        block = i.to_bytes(4, 'big')
                        block += len(data).to_bytes(4, 'big')
                        block += data
                        block += bytes(4)
                        prog = 100 * (i + 1) / total_blocks
                        if self.port.write(block) != len(block):
                            logging.error("Printing FAILED: "
                                          "communication error")

                        if not self._ack():
                            logging.error("Printing FAILED: "
                                          "cannot write data to the printer!")
                            self._upload = None
                            self.message_callback(
                                b'upload:{"stat":"complete"}'
                            )
                            break
                        msg = 'upload:{"stat":"uploading",'
                        msg += f'"progress":{prog}}}'
                        self.message_callback(msg.encode())

                    while not self._ack():
                        self.sendaction('', func='uploadDidFinish')
                        time.sleep(0.1)
                    self.message_callback(b'upload:{"stat":"complete"}')
                    self._print_status = 'printing'
                    self._upload = None
                else:
                    self.query()
                    time.sleep(0.250)
            else:
                time.sleep(1)
        self.stoped = True

    def home(self):
        logging.info("Homing printer...")
        self.sendaction("home")

    def loadfilemanet(self):
        logging.info("Loading filament...")
        self.sendaction("load", "new")

    def cancelloadfilemanet(self):
        logging.info("Loading filament...")
        self.sendaction("load", "cancel")

    def unloadfilemanet(self):
        logging.info("Loading filament...")
        self.sendaction("unload", "new")

    def cancelunloadfilemanet(self):
        logging.info("Loading filament...")
        self.sendaction("unload", "cancel")

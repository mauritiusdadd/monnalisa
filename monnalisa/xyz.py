"""
Maurizio D'Addona <mauritiusdadd@gmail.com> (c) 2019 - 2020

monnalisa is a program to control da vinci printers
Copyright (C) 2013-2015  Maurizio D'Addona <mauritiusdadd@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import logging
import threading
import socket
import math
import time
import os
import io
import zipfile
import zlib
import serial

from Crypto.Cipher import AES

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

MACHINES = {
    "daVinciF10": (2, True, False),
    "daVinciF10": (2, True, False),
    "daVinciF10": (2, True, False),
    "daVinciF11": (2, True, True),
    "daVinciF20": (2, True, False),
    "daVinciF20": (2, True, False),
    "daVinciJR10": (2, False, True),
    "dv1JA0A000": (2, False, True),
    "daVinciJR10W": (2, False, True),
    "dv1JSOA000": (2, False, True),
    "daVinciJR10S": (5, False, True),
    "daVinciJR20W": (2, False, True),
    "dv1MX0A000": (2, False, True),
    "dv1MW0A000": (2, False, True),
    "dv1MW0B000": (2, False, True),
    "dv1MW0C000": (2, False, True),
    "dv1NX0A000": (2, False, True),
    "dv1NW0A000": (2, False, True),
    "dv1JP0A000": (5, False, True),
    "dv1JPWA000": (5, False, True),
    "daVinciAW10": (5, False, True),
    "daVinciAS10": (5, False, True),
    "dv1SW0A000": (5, False, True),
}


XYZ_HEADER_KEYS = {
    'TIME': 'print_time',
    'LAYER_COUNT': 'total_layers',
    'Filament used': 'total_filament',
    'FLAVOR': None,
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
        logging.error("Corrupted Message: invalid crc32")
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
            self._rawbuff += self.socket.recv(4096)
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
        'home', 'load', 'unload', 'calibratejr', 'upload', 'image'
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
        self.name = ""
        self.id = ""
        self.zipped = False
        self.version = 2
        self.start()

    def stop(self):
        self._do_stop = True
        self.disconnect()
        # self.join()

    def setid(self, uid):
        try:
            specs = MACHINES[uid]
        except KeyError:
            self.id = uid
        else:
            self.id = uid
            self.version = specs[0]
            self.zipped = specs[1]

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

    def sendAck(self, resp=b''):
        ack = b'ok:' + resp + b'\n'
        self.port.write(ack)

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
                            print(fdata[0:10])
                            if not fdata.startswith(b'3DPFNKG13WTW'):
                                logging.info("Converting to 3w format...")
                                fdata = gcode2www(
                                    fdata.decode(),
                                    self.version,
                                    self.zipped,
                                    self.id
                                )
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

    def calibrationinit(self):
        logging.info("Waiting for caliration sensor...")
        self.sendaction("calibratejr", "new")

    def calibrationrun(self):
        logging.info("Calibrating...")
        self.sendaction("calibratejr", "detectorok")

    def calibrationdone(self):
        self.sendaction("calibratejr", "release")

    def jog(self, axis, jog):
        jog_dir = "+" if jog >= 0 else '-'
        jog_len = abs(jog)
        self.sendaction(
            "jog",
            f'{{"axis":"{axis}","dir":"{jog_dir}","len":"{jog_len}"}}'
        )


def gcode2www(gcode, version, zipped, machine_id):

    BODY_OFFSET = 0x2000
    PACKET_SIZE = 0x2000

    xyz_header_dict = {
        'filename': 'sample.3w',
        'print_time': 60,
        'machine': machine_id,
        'facets': 50,
        'total_layers': 10,
        'version': 18020109,
        'total_filament': 1.0,
    }

    for key in XYZ_HEADER_KEYS:
        key_start = gcode.find(f';{key}:')
        key_end = gcode.find('\n', key_start)

        if key_start < 0:
            continue

        line = gcode[key_start:key_end].replace(' ', '')
        _, val = line.split(':')
        if XYZ_HEADER_KEYS[key] is not None:
            xyz_header_dict[XYZ_HEADER_KEYS[key]] = val

    header_end = 0
    while header_end >= 0:
        header_end = gcode.find('\n', header_end+1)
        if gcode[header_end+1] != ';':
            break

    gcode_header = gcode[:header_end+1]
    gcode = gcode[header_end+1:]

    for key in xyz_header_dict:
        key_start = gcode_header.find(f'; {key} =')
        key_end = gcode_header.find('\n', key_start)

        if key_start < 0:
            continue

        line = gcode_header[key_start:key_end].replace(' ', '')
        _, val = line.split('=')
        xyz_header_dict[key] = val
        gcode_header = gcode_header[:key_start] + gcode_header[key_end+1:]

    header = '\n'.join(
        [f'; {k:s} = {v}' for k, v in xyz_header_dict.items()]
    )
    header += gcode_header
    header = header.encode()

    gcode = gcode.replace('G0 ', 'G1 ')
    gcode = gcode.replace('G00 ', 'G1 ')
    gcode = gcode.replace('G01 ', 'G1 ')
    gcode = header + gcode.encode()

    padding = pad16(len(header))
    header += bytes([padding, ]*padding)

    if version == 2:
        # encrypt the header
        aes_cbc = AES.new(
            b'@xyzprinting.com',
            AES.MODE_CBC,
            b'\x00'*16
        )
        header = aes_cbc.encrypt(header)

    if version == 2:
        if zipped:

            with io.BytesIO() as bytesio:
                with zipfile.ZipFile(bytesio, "w",
                                     zipfile.ZIP_DEFLATED) as zip_obj:
                    zip_obj.writestr("sample.3w", gcode)
                bytesio.seek(0)
                body_data = bytesio.read()

            off = 0
            body = b''
            while off < len(body_data):
                aes_cbc = AES.new(
                    b'@xyzprinting.com',
                    AES.MODE_CBC,
                    b'\x00'*16
                )
                packet = body_data[off:off + PACKET_SIZE]
                padding = pad16(len(packet))
                packed = packet + bytes([padding, ]*padding)
                body += aes_cbc.encrypt(packed)
                off += PACKET_SIZE
        else:
            aes_ecb = AES.new(b'@xyzprinting.com@xyzprinting.com',
                              AES.MODE_ECB)
            padding = pad16(len(gcode))
            body = gcode + bytes([padding, ]*padding)
            body = aes_ecb.encrypt(body)
    else:
        padding = pad16(len(gcode))
        body = gcode + bytes([padding, ]*padding)

    with io.BytesIO() as stream:
        stream.write(b'3DPFNKG13WTW')
        stream.write(bytes([1, version, 0, 0]))

        zip_start = ceil16(4688 + stream.tell()) - stream.tell() - 4

        stream.write(zip_start.to_bytes(4, byteorder='big'))
        stream.write(bytes(zip_start))

        if zipped:
            stream.write(b'TagEa128')
        else:
            stream.write(b'TagEJ256')

        if version == 5:
            stream.write(len(header).to_bytes(4, byteorder='big'))

        header_start = ceil16(68 + stream.tell()) - stream.tell() - 4
        stream.write(header_start.to_bytes(4, byteorder='big'))

        if version == 5:
            stream.write(bytes([0, 0, 0, 1]))

        stream.write(zlib.crc32(body).to_bytes(4, byteorder='big'))

        if version == 5:
            stream.write(bytes(header_start-8))
        else:
            stream.write(bytes(header_start-4))

        stream.write(header)
        stream.write(bytes(BODY_OFFSET - stream.tell()))
        stream.seek(BODY_OFFSET)
        stream.write(body)
        stream.seek(0)
        return stream.read()


def pad16(val):
    return 16 - val % 16


def ceil16(val):
    if val % 16 == 0:
        return val
    return val + pad16(val)


def floor16(val):
    return val - (val % 16)

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

import sys
import argparse
import socket
import time
import logging
import threading
import zlib
import uuid
import base64

from functools import partial

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

import monnalisa
from monnalisa import xyzgui, xyz


def client_callback(client, msg):
    try:
        client.sendall(xyz.socketmsg(msg))
    except (BrokenPipeError, ConnectionError):
        pass


class CamThread(threading.Thread):

    def __init__(self, cam, interval=1):
        super().__init__()
        self._do_stop = False
        self.cam = cam
        self.interval = interval
        self._lock = threading.Lock()
        self.start()
        self.packet_size = 1024

    def onImageCallback(self, image):
        pass

    def stop(self):
        self._do_stop = True
        self.ack()
        self.join()

    def ack(self):
        if self._lock.locked():
            self._lock.release()

    def run(self):
        while not self._do_stop:
            print('sending image...')
            ret, frame = self.cam.read()
            frame = frame[::2, ::2]
            img_id = str(uuid.uuid4()).encode()
            shape = frame.shape
            if HAS_CV2:
                data = cv2.imencode('.png', frame)[1]
            else:
                data = frame.tobytes()
            data = zlib.compress(data, 9)
            data = base64.b64encode(data)
            for off in range(0, len(data), self.packet_size):
                stripe = data[off:off+self.packet_size]
                msg = b'image:{'
                msg += b'"id":"' + img_id + b'",'
                msg += b'"shape":' + ('['+str(shape)[1:-1]+']').encode()+b','
                msg += b'"offset":' + str(off).encode() + b','
                msg += b'"data":"' + stripe + b'"}\n'
                self._lock.acquire()
                send_time = time.time()
                self.onImageCallback(msg)
                while self._lock.locked():
                    if time.time() - send_time > 10:
                        self.onImageCallback(msg)
                        send_time = time.time()
            self.onImageCallback(b'image:{"id":"' + img_id + b'"}\n')
            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description='Controls Da Vinci printers')
    parser.add_argument("--addr", type=str, nargs='?', metavar='IPADDR',
                        default=False,
                        help="Start the program as a server on the address "
                        "%(metavar)s to control the printer over the network."
                        " If no address is specified the server will be "
                        "reachable any address the machine happens to have.")
    parser.add_argument("--server-port", metavar='PORT', type=int,
                        default=2222, help="Set the port used to create the "
                        "server. If no port is psecified then the default "
                        "port 2222 is used to accept inbound connections.")
    parser.add_argument("--printer-port", '-p', metavar='PORT', type=str,
                        help="The port used to communicate with the priter.")
    parser.add_argument("--baud", '-b', metavar='BAUDRATE', type=int,
                        default=9600, help="Specify the baud rate of the "
                        "serial connection tiwth the printer. If this option "
                        "is not specified then the default vaule ob 9600 is "
                        "used")
    parser.add_argument("--version", action='store_true')

    args = parser.parse_args()

    if args.version:
        print(f"Monnalisa v{monnalisa.__version__}")
        sys.exit(0)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    clog = logging.StreamHandler()
    logger.addHandler(clog)
    clog.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s  %(levelname)s  %(message)s'
    )
    clog.setFormatter(formatter)

    if args.server:
        addr = args.server
    else:
        addr = ''

    logger.info("Creating a server on %s:%d", addr, args.server_port)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((addr, args.server_port))
    srv.listen(5)
    logger.info("Socket timeout: %s", srv.gettimeout())
    client = None

    if HAS_CV2:
        device = 0
        logger.info("Opening video stream with device %d", device)
        remote_cam = cv2.VideoCapture(0)
        cam_thread = CamThread(remote_cam, 10)

    logger.info("Creating printer object...")
    printer = xyz.XYZPrinter()
    try:
        if not printer.connect(args.printer_port, args.baud, timeout=3):
            sys.exit(1)
        while True:
            logger.info("Waiting for clients")
            client, client_addr = srv.accept()
            logger.info("New client accepted from %s", client_addr)
            _rawbuff = b''

            if HAS_CV2:
                client_send_message = partial(client_callback, client)
            printer.message_callback = client_send_message
            cam_thread.onImageCallback = client_send_message

            client_error = False
            while client:
                try:
                    data = client.recv(1024)
                    if not data:
                        client_error = True
                except ConnectionError as exc:
                    # TODO: retry
                    logging.error(exc)
                    client_error = True

                if client_error:
                    printer.message_callback = lambda x: None
                    client = None
                    break

                if data:
                    _rawbuff += data

                msg_start = _rawbuff.find(xyz.SocketPort.PACKET_START)
                while msg_start >= 0:
                    msg_start += len(xyz.SocketPort.PACKET_START)
                    msg_end = _rawbuff.find(
                        xyz.SocketPort.PACKET_END,
                        msg_start
                    )

                    if msg_end < 0:
                        break

                    action = _rawbuff[msg_start:msg_end]
                    msg_end += len(xyz.SocketPort.PACKET_END)
                    _rawbuff = _rawbuff[msg_end+1:]

                    message = xyz._parsemsg(action)
                    msg_start = _rawbuff.find(
                        xyz.SocketPort.PACKET_START,
                        msg_end
                    )
                    if message.startswith(b'ok:'):
                        if message.endswith(b':image\n'):
                            cam_thread.ack()
                    else:
                        printer.port.write(message)

    except (KeyboardInterrupt, SystemExit):
        if client:
            try:
                logging.info("Closing client %s", client.getpeername()[0])
                client.send(b'close')
            except OSError:
                pass
            else:
                client.close()
        if HAS_CV2:
            cam_thread.stop()
        printer.stop()
        srv.close()

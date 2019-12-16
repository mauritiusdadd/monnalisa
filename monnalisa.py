#!/usr/bin/env python
import sys
import argparse
import socket
import time
import logging
import threading

from functools import partial

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from monnalisa import xyzgui, xyz


def client_callback(client, msg):
    try:
        client.sendall(xyz.socketmsg(msg))
    except BrokenPipeError:
        pass


class CamThread(threading.Thread):

    def __init__(self, cam, interval=1):
        super().__init__()
        self._do_stop = False
        self.cam = cam
        self.interval = interval
        self.start()

    def onImageCallback(self, image):
        pass

    def stop(self):
        self._do_stop = True
        self.join()

    def run(self):
        while not self._do_stop:
            ret, frame = self.cam.read()
            self.onImageCallback(frame)
            time.sleep(self.interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Controls Da Vinci printers')
    parser.add_argument("--server", type=str, nargs='?', metavar='IPADDR',
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

    args = parser.parse_args()
    if args.server is False:
        xyzgui.main()
    else:
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
            cam_thread = CamThread(remote_cam, 5)

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

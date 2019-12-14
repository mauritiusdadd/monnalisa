#!/usr/bin/env python

import sys
import time
import argparse
import socket
import logging
from monnalisa import xyzgui, xyz


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Controls Da Vinci printers')
    parser.add_argument("--server", type=str, nargs='?', metavar='IPADDR',
                        default=False,
                        help="Start the program as a server on the address "
                        "%(metavar) to control the printer over the network. "
                        "If no address is specified the server will be "
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
            '%(asctime)s - %(levelname)s - %(message)s'
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
        client = None
        printer = xyz.XYZPrinter()
        try:
            if not printer.connect(args.printer_port, args.baud, timeout=1):
                sys.exit(1)
            while True:
                logger.info("Waiting for clients")
                client, client_addr = srv.accept()
                logger.info("New client accepted from %s", client_addr)
                while client:
                    print(client.recv(1024))
                    time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            if client:
                try:
                    logging.info("Closing client %s", client.getpeername()[0])
                    client.send(b'close')
                except OSError:
                    pass
                else:
                    client.close()
            srv.close()
            printer.stop()

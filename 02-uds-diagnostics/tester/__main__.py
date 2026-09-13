"""python -m tester [--channel vcan0] [--log file.log]

With --channel virtual the ECU is started in this process too, so the whole
session runs with no kernel module; --log then records exactly what went over
the (virtual) wire in candump format — that is how project 04's
samples/uds_session.log was made.
"""

from __future__ import annotations

import argparse
import logging
import sys

import can
from udsoncan.client import Client

from ecu.transport import UdsEcuOnCan
from ecu.uds_server import UdsServer
from .client import client_config, close_connection, make_connection, scripted_session


def main(argv=None):
    p = argparse.ArgumentParser(description="scripted UDS tester session")
    p.add_argument("--interface", default="socketcan")
    p.add_argument("--channel", default="vcan0", help="'virtual' also starts the ECU in-process")
    p.add_argument("--log", help="record the bus to a candump-format .log")
    args = p.parse_args(argv)
    logging.getLogger("UdsClient").setLevel(logging.CRITICAL)   # NRCs are printed by the script itself

    def open_bus():
        if args.channel == "virtual":
            return can.Bus(interface="virtual", channel="uds")
        return can.Bus(interface=args.interface, channel=args.channel)

    buses = []
    ecu = None
    logger_notifier = None
    try:
        if args.channel == "virtual":
            ecu_bus = open_bus()
            buses.append(ecu_bus)
            ecu = UdsEcuOnCan(ecu_bus, UdsServer(), verbose=True)
            ecu.start()
        if args.log:
            log_bus = open_bus()
            buses.append(log_bus)
            logger_notifier = can.Notifier(log_bus, [can.Logger(args.log)])
        tester_bus = open_bus()
        buses.append(tester_bus)
        conn = make_connection(tester_bus)
        try:
            with Client(conn, request_timeout=2, config=client_config()) as client:
                scripted_session(client)
        finally:
            close_connection(conn)
    finally:
        if logger_notifier:
            logger_notifier.stop()
        if ecu:
            ecu.stop()
        for b in buses:
            b.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

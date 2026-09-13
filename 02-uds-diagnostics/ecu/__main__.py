"""python -m ecu [--channel vcan0] [--verbose]  — the engine ECU's diagnostic side."""

from __future__ import annotations

import argparse
import sys
import time

import can

from .transport import UdsEcuOnCan
from .uds_server import UdsServer


def main(argv=None):
    p = argparse.ArgumentParser(description="UDS server for the engine ECU")
    p.add_argument("--interface", default="socketcan")
    p.add_argument("--channel", default="vcan0")
    p.add_argument("--engine-off", action="store_true", help="engine speed 0 so ECUReset is allowed")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    bus = can.Bus(interface=args.interface, channel=args.channel)
    server = UdsServer()
    if args.engine_off:
        server.state.engine_speed_rpm = 0
    ecu = UdsEcuOnCan(bus, server, verbose=args.verbose)
    ecu.start()
    print(f"ecu  listening on {args.channel}: rx 0x7E0 -> tx 0x7E8  (Ctrl-C to stop)")
    try:
        while ecu.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        ecu.stop()
        bus.shutdown()
    st = server.state
    print(f"ecu  session={st.session} unlocked={st.security_unlocked} failed_keys={st.failed_key_attempts} resets={st.resets}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

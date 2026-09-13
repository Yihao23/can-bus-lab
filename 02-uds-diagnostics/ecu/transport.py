"""ISO-TP plumbing between a CAN bus and UdsServer.

Two ways to get ISO-TP on Linux, and this file supports the one that also
works in a unit test:
  - the kernel module `can-isotp` (a socket of type CAN_ISOTP; `isotpsend` /
    `isotprecv` from can-utils talk to it) — fastest, but needs vcan and root
  - python `can-isotp` on top of python-can — used here, so the same code runs
    on vcan0 and on the in-process virtual bus
"""

from __future__ import annotations

import threading
import time

import can
import isotp

from .uds_server import NRC_RESPONSE_PENDING, UdsServer

ENGINE_RX_ID = 0x7E0   # tester -> engine ECU (physical addressing)
ENGINE_TX_ID = 0x7E8   # engine ECU -> tester
FUNCTIONAL_ID = 0x7DF  # tester -> everybody; TODO(you) — project 02, day 7

ISOTP_PARAMS = {
    "stmin": 0,            # we can take consecutive frames back to back
    "blocksize": 8,        # send a flow control every 8 CFs — visible in candump
    "tx_padding": 0xAA,    # pad to 8 bytes; 0xAA is what many OEMs use, 0x00/0x55 too
    "rx_flowcontrol_timeout": 1000,
    "rx_consecutive_frame_timeout": 1000,
}


class UdsEcuOnCan(threading.Thread):
    """Runs UdsServer behind an ISO-TP stack on `bus` until stop() is called."""

    def __init__(self, bus: can.BusABC, server: UdsServer | None = None, verbose: bool = False,
                 rxid: int = ENGINE_RX_ID, txid: int = ENGINE_TX_ID):
        super().__init__(daemon=True, name="UdsEcu")
        self.server = server or UdsServer()
        self.verbose = verbose
        self.notifier = can.Notifier(bus, [])
        addr = isotp.Address(isotp.AddressingMode.Normal_11bits, rxid=rxid, txid=txid)
        self.stack = isotp.NotifierBasedCanStack(bus, self.notifier, address=addr, params=ISOTP_PARAMS)
        self._stop = threading.Event()
        self.t0 = time.monotonic()

    def run(self):
        self.stack.start()
        try:
            while not self._stop.is_set():
                request = self.stack.recv(block=True, timeout=0.1)
                now = time.monotonic() - self.t0
                if request is None:
                    self.server.tick(now)
                    continue
                if self.verbose:
                    print(f"ecu  <- {request.hex(' ')}")
                for response in self.server.handle(bytes(request), now):
                    if self.verbose:
                        print(f"ecu  -> {response.hex(' ')}")
                    self.stack.send(response)
                    if len(response) == 3 and response[2] == NRC_RESPONSE_PENDING:
                        time.sleep(0.3)   # the "slow" service doing its slow thing
        finally:
            self.stack.stop()
            self.notifier.stop()

    def stop(self):
        self._stop.set()
        self.join(timeout=2)

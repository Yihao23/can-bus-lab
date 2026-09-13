"""A diagnostic tester built on udsoncan. One scripted session that touches
every service the ECU implements — the "workshop tool" side of the wire.
"""

from __future__ import annotations

import argparse
import sys

import can
import isotp
import udsoncan
from udsoncan.client import Client
from udsoncan.connections import PythonIsoTpConnection
from udsoncan.exceptions import NegativeResponseException

from ecu.uds_server import compute_key   # the tester must know the algorithm; the ECU's copy is the truth
from ecu.transport import ENGINE_RX_ID, ENGINE_TX_ID, ISOTP_PARAMS


class AsciiCodec(udsoncan.DidCodec):
    """Fixed-length text DID. udsoncan needs to know each DID's length to
    split a multi-DID response — there is no delimiter on the wire, only the
    tester's own configuration tells it where one value ends. That is why a
    tester without the ECU's DID table cannot decode a multi-DID reply."""

    def __init__(self, length: int):
        self.length = length

    def encode(self, s):
        return s.encode().ljust(self.length, b"\x00")

    def decode(self, b):
        return b.rstrip(b"\x00").decode(errors="replace")

    def __len__(self):
        return self.length


def client_config() -> dict:
    cfg = dict(udsoncan.configs.default_client_config)
    cfg["data_identifiers"] = {
        0xF190: AsciiCodec(17), 0xF187: AsciiCodec(15), 0xF18C: AsciiCodec(8), 0xF195: AsciiCodec(5),
        0xF1A0: AsciiCodec(13), 0x0100: ">H", 0x0101: ">B", 0x0200: ">H",
        0xDEAD: ">B",   # configured on the tester, unknown to the ECU -> NRC 0x31, which is the lesson
    }
    cfg["security_algo"] = lambda level, seed, params=None: compute_key(seed)
    cfg["p2_timeout"] = 1.0
    cfg["p2_star_timeout"] = 6.0
    cfg["exception_on_negative_response"] = True
    return cfg


def make_connection(bus: can.BusABC) -> PythonIsoTpConnection:
    notifier = can.Notifier(bus, [])
    addr = isotp.Address(isotp.AddressingMode.Normal_11bits, rxid=ENGINE_TX_ID, txid=ENGINE_RX_ID)
    stack = isotp.NotifierBasedCanStack(bus, notifier, address=addr, params=ISOTP_PARAMS)
    conn = PythonIsoTpConnection(stack)
    conn._lab_notifier = notifier   # keep it alive; stopped in close_connection()
    return conn


def close_connection(conn: PythonIsoTpConnection):
    conn.close()
    conn._lab_notifier.stop()


def scripted_session(client: Client, out=print) -> dict:
    """Returns a dict of what was observed, so the test can assert on it."""
    seen: dict = {}

    def step(label, fn):
        try:
            r = fn()
            seen[label] = r
            out(f"tester  {label:<34} OK   {r}")
        except NegativeResponseException as e:
            seen[label] = f"NRC 0x{e.response.code:02X} {e.response.code_name}"
            out(f"tester  {label:<34} NRC  0x{e.response.code:02X} {e.response.code_name}")
        except Exception as e:  # timeouts, invalid responses
            seen[label] = f"ERR {type(e).__name__}: {e}"
            out(f"tester  {label:<34} ERR  {type(e).__name__}: {e}")

    step("read VIN in default session", lambda: client.read_data_by_identifier(0xF190).service_data.values[0xF190])
    step("read live engine speed (raw)", lambda: client.read_data_by_identifier(0x0100).service_data.values[0x0100][0])
    step("read secured DID while locked", lambda: client.read_data_by_identifier(0xF1A0).service_data.values[0xF1A0])
    step("security access in default session", lambda: client.unlock_security_access(1))
    step("enter extended session", lambda: client.change_session(3).service_data.session_echo)
    step("security access (seed/key)", lambda: client.unlock_security_access(1).positive)
    step("read secured DID now", lambda: client.read_data_by_identifier(0xF1A0).service_data.values[0xF1A0])
    step("read three DIDs at once", lambda: client.read_data_by_identifier([0xF187, 0xF18C, 0xF195]).service_data.values)
    step("read unknown DID", lambda: client.read_data_by_identifier(0xDEAD).service_data.values)
    step("read slow DID (expect 0x78 first)", lambda: client.read_data_by_identifier(0x0200).service_data.values[0x0200][0])
    step("count DTCs status mask 0x09", lambda: client.read_dtc_information(0x01, status_mask=0x09).service_data.dtc_count)
    step("list DTCs status mask 0xFF",
         lambda: [(f"{d.id:06X}", d.status.get_byte_as_int()) for d in client.read_dtc_information(0x02, status_mask=0xFF).service_data.dtcs])
    step("tester present", lambda: client.tester_present().positive)
    step("ECU reset while engine runs", lambda: client.ecu_reset(1).positive)
    return seen


def main(argv=None):
    p = argparse.ArgumentParser(description="scripted UDS tester session")
    p.add_argument("--interface", default="socketcan")
    p.add_argument("--channel", default="vcan0")
    args = p.parse_args(argv)
    bus = can.Bus(interface=args.interface, channel=args.channel)
    conn = make_connection(bus)
    try:
        with Client(conn, request_timeout=2, config=client_config()) as client:
            scripted_session(client)
    finally:
        close_connection(conn)
        bus.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

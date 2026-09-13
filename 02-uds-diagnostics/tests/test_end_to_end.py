"""ECU and tester on the same in-process virtual bus, real ISO-TP, real udsoncan.
Slow (seconds) because ISO-TP timing is real. No vcan, no sudo."""
import unittest

import can
from udsoncan.client import Client

from ecu.transport import UdsEcuOnCan
from ecu.uds_server import UdsServer
from tester.client import client_config, close_connection, make_connection, scripted_session


class EndToEndTest(unittest.TestCase):
    def test_scripted_session(self):
        ecu_bus = can.Bus(interface="virtual", channel="uds-test")
        tester_bus = can.Bus(interface="virtual", channel="uds-test")
        server = UdsServer()
        ecu = UdsEcuOnCan(ecu_bus, server)
        ecu.start()
        conn = make_connection(tester_bus)
        try:
            with Client(conn, request_timeout=2, config=client_config()) as client:
                seen = scripted_session(client, out=lambda *_: None)
        finally:
            close_connection(conn)
            ecu.stop()
            ecu_bus.shutdown()
            tester_bus.shutdown()

        self.assertEqual(seen["read VIN in default session"], "WCANLAB0000000001")
        self.assertEqual(seen["read secured DID while locked"], "NRC 0x33 SecurityAccessDenied")
        self.assertEqual(seen["security access in default session"], "NRC 0x7F ServiceNotSupportedInActiveSession")
        self.assertEqual(seen["enter extended session"], 3)
        self.assertIs(seen["security access (seed/key)"], True)
        self.assertEqual(seen["read secured DID now"], "CAL-2026-09-A")
        self.assertEqual(set(seen["read three DIDs at once"]), {0xF187, 0xF18C, 0xF195})
        self.assertEqual(seen["read unknown DID"], "NRC 0x31 RequestOutOfRange")
        self.assertEqual(seen["read slow DID (expect 0x78 first)"], 0xDEAD)   # udsoncan waited P2* through the 0x78
        self.assertEqual(seen["count DTCs status mask 0x09"], 2)
        self.assertEqual(len(seen["list DTCs status mask 0xFF"]), 3)
        self.assertIs(seen["tester present"], True)
        self.assertEqual(seen["ECU reset while engine runs"], "NRC 0x22 ConditionsNotCorrect")
        self.assertTrue(server.state.security_unlocked)


if __name__ == "__main__":
    unittest.main()

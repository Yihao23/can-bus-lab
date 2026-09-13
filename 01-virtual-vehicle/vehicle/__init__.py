"""A three-ECU virtual vehicle on a CAN bus.

Everything here runs on python-can, so it works on a Linux vcan interface
(where candump / Wireshark can see it) and on python-can's in-process
'virtual' interface (where the tests run with no kernel module and no sudo).
"""

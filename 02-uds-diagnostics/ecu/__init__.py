"""A UDS (ISO 14229) server for the engine ECU of project 01.

`uds_server.py` is pure logic: bytes in, list of bytes out, no sockets, no
threads. That is what makes it testable in milliseconds and what lets the same
code sit behind kernel ISO-TP, python can-isotp, or a unit test.
纯逻辑: 字节进、字节列表出，没有 socket 和线程。所以它能在毫秒内被测试，
也能同样地挂在内核 ISO-TP、python can-isotp 或单元测试后面。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# --- ISO 14229-1 constants ---------------------------------------------------

SID_DIAGNOSTIC_SESSION_CONTROL = 0x10
SID_ECU_RESET = 0x11
SID_CLEAR_DIAGNOSTIC_INFORMATION = 0x14
SID_READ_DTC_INFORMATION = 0x19
SID_READ_DATA_BY_IDENTIFIER = 0x22
SID_SECURITY_ACCESS = 0x27
SID_WRITE_DATA_BY_IDENTIFIER = 0x2E
SID_TESTER_PRESENT = 0x3E

NEGATIVE_RESPONSE = 0x7F
POSITIVE_OFFSET = 0x40
SUPPRESS_POS_RSP = 0x80  # bit 7 of the sub-function byte

NRC_GENERAL_REJECT = 0x10
NRC_SERVICE_NOT_SUPPORTED = 0x11
NRC_SUBFUNCTION_NOT_SUPPORTED = 0x12
NRC_INCORRECT_LENGTH = 0x13
NRC_CONDITIONS_NOT_CORRECT = 0x22
NRC_REQUEST_SEQUENCE_ERROR = 0x24
NRC_REQUEST_OUT_OF_RANGE = 0x31
NRC_SECURITY_ACCESS_DENIED = 0x33
NRC_INVALID_KEY = 0x35
NRC_EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
NRC_RESPONSE_PENDING = 0x78
NRC_SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7F

SESSION_DEFAULT = 0x01
SESSION_PROGRAMMING = 0x02
SESSION_EXTENDED = 0x03

# 0x10 positive response carries the server's timing so the tester can size
# its timeouts: P2 in 1 ms units, P2* in 10 ms units.
P2_SERVER_MAX_MS = 50
P2_STAR_SERVER_MAX_MS = 5000
S3_SERVER_MS = 5000          # no TesterPresent for this long -> back to default session

SECURITY_LEVEL_1 = 0x01      # requestSeed; the key sub-function is level + 1

# --- DTCs: 3-byte DTC + 1 status byte, ISO 14229 / ISO 15031 format --------------
# Status bits: 0x01 testFailed, 0x04 pendingDTC, 0x08 confirmedDTC, 0x40 testNotCompletedThisOperationCycle
DEFAULT_DTCS: dict[int, int] = {
    0x011F00: 0x09,   # P011F coolant temp sensor rationality: testFailed + confirmed
    0xC07300: 0x08,   # U0073 bus-off on CAN 1: confirmed
    0x030100: 0x04,   # P0301 misfire cyl 1: pending only
}

DEFAULT_DIDS: dict[int, bytes] = {
    0xF190: b"WCANLAB0000000001",       # VIN, 17 chars
    0xF187: b"CANLAB-ENG-0001",          # spare part number
    0xF18C: b"SN000042",                 # serial number
    0xF195: b"1.0.3",                    # software version
}
DID_ENGINE_SPEED = 0x0100     # live, uint16, 0.25 rpm/bit — same scaling as the DBC
DID_COOLANT_TEMP = 0x0101     # live, uint8, offset -40
DID_CALIBRATION_ID = 0xF1A0   # security-protected
DID_SLOW = 0x0200             # answers 0x78 first, then the value — for P2* practice


@dataclass
class ServerState:
    session: int = SESSION_DEFAULT
    security_unlocked: bool = False
    pending_seed: bytes | None = None
    failed_key_attempts: int = 0
    last_tester_activity: float = 0.0
    dtcs: dict[int, int] = field(default_factory=lambda: dict(DEFAULT_DTCS))
    dids: dict[int, bytes] = field(default_factory=lambda: dict(DEFAULT_DIDS))
    engine_speed_rpm: float = 850.0
    coolant_temp_c: float = 62.0
    resets: int = 0


def negative(sid: int, nrc: int) -> bytes:
    return bytes([NEGATIVE_RESPONSE, sid, nrc])


def positive(sid: int, *payload: bytes | int) -> bytes:
    out = bytearray([sid + POSITIVE_OFFSET])
    for p in payload:
        out += bytes([p]) if isinstance(p, int) else p
    return bytes(out)


def compute_key(seed: bytes) -> bytes:
    """Seed/key algorithm. Deliberately trivial and deliberately *documented*:
    an OEM's real one is secret, but its shape — fixed function of the seed,
    known to tester and ECU — is exactly this.
    故意简单、故意公开: OEM 的真算法是保密的，但形状就是这样 —— 种子的固定函数，
    诊断仪和 ECU 都知道。"""
    return bytes(((b ^ 0xA5) + i) & 0xFF for i, b in enumerate(seed))


class UdsServer:
    """`handle(request, now) -> list[bytes]` — zero, one or two responses.
    Two happen when the service is slow: first NRC 0x78, then the real answer.
    """

    def __init__(self, seed_source=None):
        self.state = ServerState()
        self._seed_source = seed_source or (lambda: bytes([0x12, 0x34, 0x56, 0x78]))
        self._handlers = {
            SID_DIAGNOSTIC_SESSION_CONTROL: self._session_control,
            SID_ECU_RESET: self._ecu_reset,
            SID_READ_DTC_INFORMATION: self._read_dtc,
            SID_READ_DATA_BY_IDENTIFIER: self._read_did,
            SID_SECURITY_ACCESS: self._security_access,
            SID_TESTER_PRESENT: self._tester_present,
            # TODO(you) — project 02, day 6: SID_CLEAR_DIAGNOSTIC_INFORMATION (0x14)
            # and SID_WRITE_DATA_BY_IDENTIFIER (0x2E). See the README for the
            # rules each must enforce. Until then they answer 0x11.
        }

    # -- entry points ---------------------------------------------------------

    def handle(self, request: bytes, now: float = 0.0) -> list[bytes]:
        self.tick(now)
        if not request:
            return [negative(0x00, NRC_INCORRECT_LENGTH)]
        sid = request[0]
        self.state.last_tester_activity = now
        handler = self._handlers.get(sid)
        if handler is None:
            return [negative(sid, NRC_SERVICE_NOT_SUPPORTED)]
        responses = handler(request, now)
        return [r for r in responses if r is not None]

    def tick(self, now: float):
        """S3 timer. Call it periodically even when nothing arrives — the
        whole point is to notice that nothing arrived.
        S3 定时器。没有报文到达时也要周期性调用 —— 意义恰恰是发现"什么都没来"。"""
        st = self.state
        if st.session != SESSION_DEFAULT and now - st.last_tester_activity > S3_SERVER_MS / 1000.0:
            self._enter_session(SESSION_DEFAULT)

    # -- helpers ----------------------------------------------------------------

    def _enter_session(self, session: int):
        st = self.state
        st.session = session
        # Any session change locks the ECU again. The seed handed out earlier is
        # void too, otherwise a tester could fetch a seed in extended, drop to
        # default, come back and still hold a valid seed.
        st.security_unlocked = False
        st.pending_seed = None

    @staticmethod
    def _subfunction(request: bytes) -> tuple[int, bool]:
        sf = request[1]
        return sf & 0x7F, bool(sf & SUPPRESS_POS_RSP)

    # -- 0x10 DiagnosticSessionControl ------------------------------------------

    def _session_control(self, req: bytes, now: float) -> list[bytes | None]:
        sid = req[0]
        if len(req) != 2:
            return [negative(sid, NRC_INCORRECT_LENGTH)]
        session, suppress = self._subfunction(req)
        if session not in (SESSION_DEFAULT, SESSION_PROGRAMMING, SESSION_EXTENDED):
            return [negative(sid, NRC_SUBFUNCTION_NOT_SUPPORTED)]
        if session == SESSION_PROGRAMMING and self.state.session == SESSION_DEFAULT:
            # ISO 14229 lets an ECU refuse default -> programming directly;
            # most OEMs require extended first. This one does.
            return [negative(sid, NRC_CONDITIONS_NOT_CORRECT)]
        self._enter_session(session)
        self.state.last_tester_activity = now
        if suppress:
            return [None]
        timing = struct.pack(">HH", P2_SERVER_MAX_MS, P2_STAR_SERVER_MAX_MS // 10)
        return [positive(sid, session, timing)]

    # -- 0x11 ECUReset ----------------------------------------------------------

    def _ecu_reset(self, req: bytes, now: float) -> list[bytes | None]:
        sid = req[0]
        if len(req) != 2:
            return [negative(sid, NRC_INCORRECT_LENGTH)]
        if self.state.session == SESSION_DEFAULT:
            return [negative(sid, NRC_SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)]
        reset_type, suppress = self._subfunction(req)
        if reset_type not in (0x01, 0x02, 0x03):   # hard, keyOffOn, soft
            return [negative(sid, NRC_SUBFUNCTION_NOT_SUPPORTED)]
        if self.state.engine_speed_rpm > 0:
            # You do not reset a running engine controller. Real ECUs check this.
            return [negative(sid, NRC_CONDITIONS_NOT_CORRECT)]
        response = None if suppress else positive(sid, reset_type)
        self.state.resets += 1
        self._enter_session(SESSION_DEFAULT)   # a reset lands you in default
        return [response]

    # -- 0x22 ReadDataByIdentifier ------------------------------------------------

    def _read_did(self, req: bytes, now: float) -> list[bytes | None]:
        sid = req[0]
        body = req[1:]
        if len(body) == 0 or len(body) % 2:
            return [negative(sid, NRC_INCORRECT_LENGTH)]
        dids = [struct.unpack(">H", body[i:i + 2])[0] for i in range(0, len(body), 2)]
        out = bytearray()
        pending: list[bytes] = []
        for did in dids:
            value = self._did_value(did)
            if value is None:
                # ISO 14229: if *none* of the requested DIDs is supported -> 0x31.
                # If some are, the unsupported ones are silently skipped. Test it.
                continue
            if did == DID_CALIBRATION_ID and not self.state.security_unlocked:
                return [negative(sid, NRC_SECURITY_ACCESS_DENIED)]
            if did == DID_SLOW:
                pending = [negative(sid, NRC_RESPONSE_PENDING)]
            out += struct.pack(">H", did) + value
        if not out:
            return [negative(sid, NRC_REQUEST_OUT_OF_RANGE)]
        return pending + [positive(sid, bytes(out))]

    def _did_value(self, did: int) -> bytes | None:
        st = self.state
        if did == DID_ENGINE_SPEED:
            return struct.pack(">H", int(st.engine_speed_rpm / 0.25))
        if did == DID_COOLANT_TEMP:
            return bytes([int(st.coolant_temp_c) + 40])
        if did == DID_CALIBRATION_ID:
            return b"CAL-2026-09-A"
        if did == DID_SLOW:
            return b"\xDE\xAD"
        return st.dids.get(did)

    # -- 0x27 SecurityAccess ------------------------------------------------------

    def _security_access(self, req: bytes, now: float) -> list[bytes | None]:
        sid = req[0]
        if len(req) < 2:
            return [negative(sid, NRC_INCORRECT_LENGTH)]
        if self.state.session == SESSION_DEFAULT:
            return [negative(sid, NRC_SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)]
        sf, suppress = self._subfunction(req)
        st = self.state
        if sf == SECURITY_LEVEL_1:                     # requestSeed
            if len(req) != 2:
                return [negative(sid, NRC_INCORRECT_LENGTH)]
            if st.security_unlocked:
                # Already unlocked: the standard says answer with an all-zero seed.
                return [positive(sid, sf, bytes(4))]
            # TODO(you) — project 02, day 6: after 3 wrong keys, refuse seeds with
            # NRC 0x36, and after a 10 s delay accept again (0x37 while waiting).
            # Track it in st.failed_key_attempts; `now` is your clock.
            # 三次错误密钥后拒绝发种子(0x36)，等 10 s 后再接受(等待期间答 0x37)。
            st.pending_seed = self._seed_source()
            return [positive(sid, sf, st.pending_seed)]
        if sf == SECURITY_LEVEL_1 + 1:                 # sendKey
            if st.pending_seed is None:
                return [negative(sid, NRC_REQUEST_SEQUENCE_ERROR)]
            key = req[2:]
            if len(key) != len(st.pending_seed):
                return [negative(sid, NRC_INCORRECT_LENGTH)]
            if key != compute_key(st.pending_seed):
                st.failed_key_attempts += 1
                st.pending_seed = None                 # one seed, one try
                return [negative(sid, NRC_INVALID_KEY)]
            st.security_unlocked = True
            st.failed_key_attempts = 0
            st.pending_seed = None
            return [None if suppress else positive(sid, sf)]
        return [negative(sid, NRC_SUBFUNCTION_NOT_SUPPORTED)]

    # -- 0x19 ReadDTCInformation --------------------------------------------------

    def _read_dtc(self, req: bytes, now: float) -> list[bytes | None]:
        sid = req[0]
        if len(req) < 2:
            return [negative(sid, NRC_INCORRECT_LENGTH)]
        sf = req[1] & 0x7F
        availability_mask = 0x4D   # which status bits this ECU implements
        if sf == 0x01:             # reportNumberOfDTCByStatusMask
            if len(req) != 3:
                return [negative(sid, NRC_INCORRECT_LENGTH)]
            count = sum(1 for status in self.state.dtcs.values() if status & req[2])
            # format identifier 0x01 = ISO 14229-1 DTC format
            return [positive(sid, sf, availability_mask, 0x01, struct.pack(">H", count))]
        if sf == 0x02:             # reportDTCByStatusMask
            if len(req) != 3:
                return [negative(sid, NRC_INCORRECT_LENGTH)]
            out = bytearray([sf, availability_mask])
            for dtc, status in sorted(self.state.dtcs.items()):
                if status & req[2]:
                    out += dtc.to_bytes(3, "big") + bytes([status])
            return [positive(sid, bytes(out))]
        return [negative(sid, NRC_SUBFUNCTION_NOT_SUPPORTED)]

    # -- 0x3E TesterPresent -------------------------------------------------------

    def _tester_present(self, req: bytes, now: float) -> list[bytes | None]:
        sid = req[0]
        if len(req) != 2:
            return [negative(sid, NRC_INCORRECT_LENGTH)]
        sf, suppress = self._subfunction(req)
        if sf != 0x00:
            return [negative(sid, NRC_SUBFUNCTION_NOT_SUPPORTED)]
        return [None if suppress else positive(sid, 0x00)]

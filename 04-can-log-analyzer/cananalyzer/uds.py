"""ISO 14229 decoding and request/response pairing."""

from __future__ import annotations

from dataclasses import dataclass

from .isotp import IsoTpMessage

SERVICES = {
    0x10: "DiagnosticSessionControl", 0x11: "ECUReset", 0x14: "ClearDiagnosticInformation",
    0x19: "ReadDTCInformation", 0x22: "ReadDataByIdentifier", 0x23: "ReadMemoryByAddress",
    0x27: "SecurityAccess", 0x28: "CommunicationControl", 0x2A: "ReadDataByPeriodicIdentifier",
    0x2C: "DynamicallyDefineDataIdentifier", 0x2E: "WriteDataByIdentifier", 0x2F: "InputOutputControlByIdentifier",
    0x31: "RoutineControl", 0x34: "RequestDownload", 0x35: "RequestUpload", 0x36: "TransferData",
    0x37: "RequestTransferExit", 0x3D: "WriteMemoryByAddress", 0x3E: "TesterPresent",
    0x85: "ControlDTCSetting", 0x86: "ResponseOnEvent", 0x87: "LinkControl",
}

NRCS = {
    0x10: "generalReject", 0x11: "serviceNotSupported", 0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat", 0x14: "responseTooLong", 0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect", 0x24: "requestSequenceError", 0x25: "noResponseFromSubnetComponent",
    0x26: "failurePreventsExecutionOfRequestedAction", 0x31: "requestOutOfRange", 0x33: "securityAccessDenied",
    0x35: "invalidKey", 0x36: "exceededNumberOfAttempts", 0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted", 0x71: "transferDataSuspended", 0x72: "generalProgrammingFailure",
    0x73: "wrongBlockSequenceCounter", 0x78: "requestCorrectlyReceivedResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession", 0x7F: "serviceNotSupportedInActiveSession",
}

NEGATIVE = 0x7F
RESPONSE_PENDING = 0x78

# Default ISO 15765-4 physical request/response pairs. Extendable via CLI.
DEFAULT_PAIRS = {0x7E0 + i: 0x7E8 + i for i in range(8)}
FUNCTIONAL_ID = 0x7DF


@dataclass
class UdsMessage:
    src: IsoTpMessage
    sid: int                  # request SID; for responses, the SID it answers
    is_response: bool
    negative: bool
    nrc: int | None
    subfunction: int | None
    suppress_positive: bool

    @property
    def service(self) -> str:
        return SERVICES.get(self.sid, f"SID 0x{self.sid:02X}")

    def describe(self) -> str:
        p = self.src.payload
        if self.negative:
            return f"NRC 0x{self.nrc:02X} {NRCS.get(self.nrc, '?')}"
        if self.is_response:
            return f"{self.service} +  {p[1:9].hex(' ')}{'…' if len(p) > 9 else ''}"
        return f"{self.service}  {p[1:9].hex(' ')}{'…' if len(p) > 9 else ''}"


@dataclass
class Transaction:
    request: UdsMessage
    responses: list[UdsMessage]
    final: UdsMessage | None      # last non-0x78 response, or None
    latency_ms: float | None       # first byte of request -> last byte of final response

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self.responses if r.negative and r.nrc == RESPONSE_PENDING)


def decode(msg: IsoTpMessage, is_response: bool) -> UdsMessage | None:
    p = msg.payload
    if not p:
        return None
    if is_response and p[0] == NEGATIVE:
        if len(p) < 3:
            return None
        return UdsMessage(msg, p[1], True, True, p[2], None, False)
    if is_response:
        sid = p[0] - 0x40
    else:
        sid = p[0]
    sf = p[1] & 0x7F if len(p) > 1 and sid in (0x10, 0x11, 0x19, 0x27, 0x28, 0x31, 0x3E, 0x85) else None
    suppress = bool(p[1] & 0x80) if sf is not None and not is_response else False
    return UdsMessage(msg, sid, is_response, False, None, sf, suppress)


def pair(messages: list[IsoTpMessage], pairs: dict[int, int] = DEFAULT_PAIRS) -> tuple[list[Transaction], list[UdsMessage]]:
    """Walk the ISO-TP messages in time order. A request opens a transaction
    on (req_id -> resp_id); the next responses with matching SID belong to it
    until a non-0x78 one closes it. Returns (transactions, orphan responses)."""
    resp_to_req = {v: k for k, v in pairs.items()}
    open_by_resp_id: dict[int, Transaction] = {}
    transactions: list[Transaction] = []
    orphans: list[UdsMessage] = []

    for m in messages:
        if not m.complete:
            continue
        if m.can_id in pairs or m.can_id == FUNCTIONAL_ID:
            req = decode(m, is_response=False)
            if req is None:
                continue
            resp_ids = list(pairs.values()) if m.can_id == FUNCTIONAL_ID else [pairs[m.can_id]]
            for rid in resp_ids:
                tx = Transaction(req, [], None, None)
                open_by_resp_id[rid] = tx
                if rid == resp_ids[0]:
                    transactions.append(tx)
        elif m.can_id in resp_to_req:
            resp = decode(m, is_response=True)
            if resp is None:
                continue
            tx = open_by_resp_id.get(m.can_id)
            if tx is None or tx.request.sid != resp.sid:
                orphans.append(resp)
                continue
            tx.responses.append(resp)
            if not (resp.negative and resp.nrc == RESPONSE_PENDING):
                tx.final = resp
                tx.latency_ms = (m.ts_last - tx.request.src.ts_first) * 1000
                del open_by_resp_id[m.can_id]
    return transactions, orphans

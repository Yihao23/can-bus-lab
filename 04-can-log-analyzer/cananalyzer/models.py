from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Frame:
    index: int            # 0-based position in the log; the "line number" a finding points at
    ts: float             # seconds, absolute (candump -L) or relative — rules only use differences
    channel: str
    can_id: int
    data: bytes
    extended: bool = False
    fd: bool = False
    remote: bool = False

    @property
    def id_str(self) -> str:
        return f"{self.can_id:08X}" if self.extended else f"{self.can_id:03X}"


@dataclass
class Signal:
    name: str
    start: int
    length: int
    little_endian: bool   # DBC '@1' = Intel, '@0' = Motorola
    signed: bool
    factor: float
    offset: float
    unit: str


@dataclass
class MessageDef:
    can_id: int
    name: str
    dlc: int
    sender: str
    signals: list[Signal] = field(default_factory=list)
    cycle_ms: float | None = None
    e2e_data_id: int | None = None


SEVERITIES = ("ERROR", "WARNING", "INFO")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    ts: float
    frame_index: int | None
    subject: str          # message name or ID, or "bus", or "UDS"
    message: str

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(self.severity)

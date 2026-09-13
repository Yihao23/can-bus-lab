"""The rules. Each is a function (ctx) -> list[Finding]. Add one, register it
in RULES, write its test. Rules never import from projects 01 or 02 — the CRC
below is re-implemented on purpose: a diagnostic tool must not depend on the
implementation it is diagnosing.
每条规则是 (ctx) -> list[Finding]。CRC 是故意重新实现的: 诊断工具不能依赖它所诊断的实现。
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from . import isotp as isotp_mod
from . import uds as uds_mod
from .models import Finding, Frame, MessageDef

# --- the same E2E layout project 01 uses; if the bus under test used another,
# --- this is the one place to change ---------------------------------------------
E2E_COUNTER_BYTE = 6
E2E_CRC_BYTE = 7
E2E_COUNTER_MAX = 14


def crc8_j1850(data: bytes) -> int:
    crc = 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0xFF


def frame_bits_worst_case(dlc: int, extended: bool) -> int:
    base = (67 if extended else 47) + 8 * dlc
    return base + (base - 13 - 1) // 4


@dataclass
class Context:
    frames: list[Frame]
    dbc: dict[int, MessageDef]
    bitrate: int = 500_000
    busload_limit: float = 0.70
    p2_ms: float = 50.0
    p2_star_ms: float = 5000.0
    uds_pairs: dict[int, int] = field(default_factory=lambda: dict(uds_mod.DEFAULT_PAIRS))
    # filled by prepare()
    by_id: dict[int, list[Frame]] = field(default_factory=dict)
    cycle_ms: dict[int, float] = field(default_factory=dict)      # expected, from DBC or learned
    cycle_source: dict[int, str] = field(default_factory=dict)
    isotp: isotp_mod.IsoTpResult | None = None
    transactions: list = field(default_factory=list)
    orphans: list = field(default_factory=list)

    @property
    def t_start(self) -> float:
        return self.frames[0].ts if self.frames else 0.0

    @property
    def t_end(self) -> float:
        return self.frames[-1].ts if self.frames else 0.0


def prepare(ctx: Context) -> Context:
    by_id: dict[int, list[Frame]] = defaultdict(list)
    for f in ctx.frames:
        by_id[f.can_id].append(f)
    ctx.by_id = dict(by_id)
    diag_ids = set(ctx.uds_pairs) | set(ctx.uds_pairs.values()) | {uds_mod.FUNCTIONAL_ID}
    for can_id, frames in ctx.by_id.items():
        if can_id in diag_ids:
            continue
        d = ctx.dbc.get(can_id)
        if d and d.cycle_ms:
            ctx.cycle_ms[can_id] = d.cycle_ms
            ctx.cycle_source[can_id] = "dbc"
        elif len(frames) >= 10:
            gaps = [b.ts - a.ts for a, b in zip(frames, frames[1:])]
            med = statistics.median(gaps)
            # Only call it cyclic if *most* gaps sit tight around the median.
            # Not the standard deviation: one 800 ms hole in a 100 ms message
            # is exactly what we want to report, not what should stop us from
            # learning the cycle. Not the median absolute deviation either: an
            # event message that comes in bursts of two has a MAD of zero.
            # 不用标准差: 一个 800 ms 的洞正是要报告的东西。也不用 MAD: 成对突发的事件报文 MAD 为零。
            tight = sum(1 for g in gaps if abs(g - med) <= med * 0.2)
            if med > 0 and tight >= 0.7 * len(gaps):
                ctx.cycle_ms[can_id] = med * 1000
                ctx.cycle_source[can_id] = "learned"
    ctx.isotp = isotp_mod.reassemble(ctx.frames, diag_ids)
    ctx.transactions, ctx.orphans = uds_mod.pair(ctx.isotp.messages, ctx.uds_pairs)
    return ctx


def _name(ctx: Context, can_id: int) -> str:
    d = ctx.dbc.get(can_id)
    return d.name if d else f"0x{can_id:X}"


# --- R001 cycle time -------------------------------------------------------------

def rule_cycle_time(ctx: Context) -> list[Finding]:
    out = []
    for can_id, expected in ctx.cycle_ms.items():
        frames = ctx.by_id[can_id]
        limit = expected * 1.5 / 1000
        for a, b in zip(frames, frames[1:]):
            gap = b.ts - a.ts
            if gap > limit:
                missed = round(gap * 1000 / expected) - 1
                out.append(Finding("R001", "WARNING", b.ts, b.index, _name(ctx, can_id),
                                   f"gap of {gap*1000:.1f} ms, expected {expected:.0f} ms "
                                   f"({ctx.cycle_source[can_id]}) — ~{missed} frame(s) missing"))
    return out


# --- R002 message stopped ---------------------------------------------------------

def rule_message_stopped(ctx: Context) -> list[Finding]:
    out = []
    for can_id, expected in ctx.cycle_ms.items():
        last = ctx.by_id[can_id][-1]
        silent = ctx.t_end - last.ts
        if silent > 5 * expected / 1000:
            out.append(Finding("R002", "ERROR", last.ts, last.index, _name(ctx, can_id),
                               f"stopped {silent:.2f} s before the end of the log (cycle {expected:.0f} ms)"))
    return out


# --- R003 alive counter / R004 CRC ---------------------------------------------------

def _e2e_ids(ctx: Context):
    return [(cid, d) for cid, d in ctx.dbc.items() if d.e2e_data_id is not None and cid in ctx.by_id]


def rule_alive_counter(ctx: Context) -> list[Finding]:
    out = []
    for can_id, d in _e2e_ids(ctx):
        last = None
        for f in ctx.by_id[can_id]:
            if len(f.data) != 8:
                continue
            c = f.data[E2E_COUNTER_BYTE] & 0x0F
            if last is not None:
                expected = 0 if last >= E2E_COUNTER_MAX else last + 1
                if c == last:
                    out.append(Finding("R003", "ERROR", f.ts, f.index, d.name, f"alive counter repeated ({c})"))
                elif c != expected:
                    delta = (c - last) % (E2E_COUNTER_MAX + 1)
                    sev = "WARNING" if 1 < delta <= 3 else "ERROR"
                    out.append(Finding("R003", sev, f.ts, f.index, d.name,
                                       f"alive counter {last} -> {c}, expected {expected} ({delta - 1} lost)"))
            last = c
    return out


def rule_crc(ctx: Context) -> list[Finding]:
    out = []
    for can_id, d in _e2e_ids(ctx):
        for f in ctx.by_id[can_id]:
            if len(f.data) != 8:
                continue
            want = crc8_j1850(bytes([d.e2e_data_id]) + f.data[:E2E_CRC_BYTE])
            if f.data[E2E_CRC_BYTE] != want:
                out.append(Finding("R004", "ERROR", f.ts, f.index, d.name,
                                   f"CRC 0x{f.data[E2E_CRC_BYTE]:02X}, computed 0x{want:02X} (DataID {d.e2e_data_id})"))
    return out


# --- R005 DLC / R006 unknown ID -------------------------------------------------------

def rule_dlc(ctx: Context) -> list[Finding]:
    out = []
    for can_id, frames in ctx.by_id.items():
        d = ctx.dbc.get(can_id)
        if d is None:
            continue
        bad = [f for f in frames if len(f.data) != d.dlc and not f.remote]
        if bad:
            f = bad[0]
            out.append(Finding("R005", "ERROR", f.ts, f.index, d.name,
                               f"DLC {len(f.data)} but DBC says {d.dlc} — {len(bad)} of {len(frames)} frames"))
    return out


def rule_unknown_id(ctx: Context) -> list[Finding]:
    if not ctx.dbc:
        return []
    diag = set(ctx.uds_pairs) | set(ctx.uds_pairs.values()) | {uds_mod.FUNCTIONAL_ID}
    out = []
    for can_id, frames in sorted(ctx.by_id.items()):
        if can_id not in ctx.dbc and can_id not in diag:
            out.append(Finding("R006", "INFO", frames[0].ts, frames[0].index, f"0x{can_id:X}",
                               f"not in DBC — {len(frames)} frames"))
    return out


# --- R007 bus load ----------------------------------------------------------------------

def busload_windows(ctx: Context, window_s: float = 1.0) -> list[tuple[float, float]]:
    """[(window start, load fraction)] — used by the rule and by the HTML plot."""
    if not ctx.frames:
        return []
    t0 = ctx.t_start
    bits: dict[int, int] = defaultdict(int)
    for f in ctx.frames:
        bits[int((f.ts - t0) / window_s)] += frame_bits_worst_case(len(f.data), f.extended)
    n = int((ctx.t_end - t0) / window_s) + 1
    return [(t0 + i * window_s, bits.get(i, 0) / (ctx.bitrate * window_s)) for i in range(n)]


def rule_busload(ctx: Context) -> list[Finding]:
    out = []
    for t, load in busload_windows(ctx):
        if load > ctx.busload_limit:
            out.append(Finding("R007", "WARNING", t, None, "bus",
                               f"load {load*100:.0f}% in the second from t={t - ctx.t_start:.0f}s "
                               f"(limit {ctx.busload_limit*100:.0f}% at {ctx.bitrate//1000} kbit/s, worst-case stuffing)"))
    return out


# --- R008 NRC / R009 unanswered / R010 ISO-TP ---------------------------------------------

def rule_negative_response(ctx: Context) -> list[Finding]:
    out = []
    for tx in ctx.transactions:
        for r in tx.responses:
            if r.negative:
                pending = r.nrc == uds_mod.RESPONSE_PENDING
                out.append(Finding("R008", "INFO" if pending else "WARNING", r.src.ts_last, r.src.frames[-1], "UDS",
                                   f"{tx.request.service} -> NRC 0x{r.nrc:02X} {uds_mod.NRCS.get(r.nrc, '?')}"))
    return out


def rule_unanswered(ctx: Context) -> list[Finding]:
    out = []
    for tx in ctx.transactions:
        if tx.request.suppress_positive and not tx.responses:
            continue   # suppressPosRspMsgIndication: silence is the correct answer
        if tx.final is None:
            budget = ctx.p2_star_ms if tx.pending_count else ctx.p2_ms
            out.append(Finding("R009", "ERROR", tx.request.src.ts_first, tx.request.src.frames[0], "UDS",
                               f"{tx.request.service} never got a final response "
                               f"({tx.pending_count} x 0x78, budget {budget:.0f} ms)"))
        elif tx.latency_ms is not None:
            budget = ctx.p2_star_ms if tx.pending_count else ctx.p2_ms
            if tx.latency_ms > budget:
                out.append(Finding("R009", "WARNING", tx.request.src.ts_first, tx.request.src.frames[0], "UDS",
                                   f"{tx.request.service} answered after {tx.latency_ms:.1f} ms (> {budget:.0f} ms)"))
    for r in ctx.orphans:
        out.append(Finding("R009", "WARNING", r.src.ts_first, r.src.frames[0], "UDS",
                           f"response {r.describe()} without a matching request"))
    return out


def rule_isotp(ctx: Context) -> list[Finding]:
    out = []
    for m in ctx.isotp.messages:
        if not m.complete:
            out.append(Finding("R010", "ERROR", m.ts_first, m.frames[0], f"0x{m.can_id:X}", f"ISO-TP: {m.error}"))
    return out


# TODO(you) — project 04, day 11
# R011 cycle-time jitter: for each cyclic ID, pstdev(gaps) > 20 % of the
#      expected cycle -> WARNING with the measured jitter. samples/jitter.log
#      was recorded with --fault jitter=10 and no rule catches it yet.
# R012 security brute force: three or more NRC 0x35 on the same request ID
#      within 60 s -> ERROR. Think about why this is an *analyzer* rule and
#      not only an ECU rule (hint: the ECU might be the thing you do not trust).
# 为什么这条规则要放在分析器里而不只放在 ECU 里? (提示: ECU 可能正是你不信任的那个东西)

RULES = [
    rule_cycle_time, rule_message_stopped, rule_alive_counter, rule_crc, rule_dlc,
    rule_unknown_id, rule_busload, rule_negative_response, rule_unanswered, rule_isotp,
]

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}


def coalesce(findings: list[Finding], keep: int = 3) -> list[Finding]:
    """A stuck counter produces one finding per frame — hundreds. Keep the
    first `keep` per (rule, severity, subject) and fold the rest into one line
    that says how many more. The JSON output keeps them all; a human does not
    need to see a stuck counter 124 times to know it is stuck.
    卡死的计数器每帧一条发现。每组只保留前几条，其余折叠成一行"还有 N 条"。"""
    seen: dict[tuple, int] = defaultdict(int)
    out: list[Finding] = []
    folded: dict[tuple, list[Finding]] = defaultdict(list)
    for f in findings:
        key = (f.rule, f.severity, f.subject)
        seen[key] += 1
        if seen[key] <= keep:
            out.append(f)
        else:
            folded[key].append(f)
    for key, rest in folded.items():
        last = rest[-1]
        out.append(Finding(key[0], key[1], rest[0].ts, rest[0].frame_index, key[2],
                           f"… {len(rest)} more like this, last at t+{last.ts - findings[0].ts:.3f}s (frame {last.frame_index})"))
    return out


def run_all(ctx: Context, fold: bool = True) -> list[Finding]:
    prepare(ctx)
    findings = [f for rule in RULES for f in rule(ctx)]
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.ts))
    if fold:
        findings = coalesce(findings)
        findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.ts))
    return findings

"""Four renderers over the same Context + findings. text for the terminal,
json for machines, md for a ticket, html for an attachment."""

from __future__ import annotations

import html
import json
from dataclasses import asdict

from . import dbc_lite
from .models import Finding
from .rules import Context, busload_windows


def _rel(ctx: Context, ts: float) -> float:
    return ts - ctx.t_start


def id_table(ctx: Context) -> list[dict]:
    rows = []
    for can_id, frames in sorted(ctx.by_id.items()):
        d = ctx.dbc.get(can_id)
        gaps = [b.ts - a.ts for a, b in zip(frames, frames[1:])]
        period = sorted(gaps)[len(gaps) // 2] * 1000 if gaps else None
        rows.append({
            "id": f"0x{can_id:X}", "name": d.name if d else "", "count": len(frames),
            "period_ms": round(period, 1) if period else None,
            "expected_ms": ctx.cycle_ms.get(can_id), "source": ctx.cycle_source.get(can_id, ""),
            "dlc": sorted({len(f.data) for f in frames}),
            "last_decoded": dbc_lite.decode_message(d, frames[-1].data) if d else {},
        })
    return rows


def render_text(ctx: Context, findings: list[Finding]) -> str:
    lines = [f"frames: {len(ctx.frames)}  ids: {len(ctx.by_id)}  duration: {ctx.t_end - ctx.t_start:.2f} s  "
             f"uds transactions: {len(ctx.transactions)}", ""]
    lines.append(f"{'id':>8} {'name':<14} {'count':>6} {'period':>8} {'expect':>8} {'dlc':>4}")
    for r in id_table(ctx):
        exp = f"{r['expected_ms']:.0f}" if r["expected_ms"] else "-"
        per = f"{r['period_ms']:.1f}" if r["period_ms"] else "-"
        lines.append(f"{r['id']:>8} {r['name']:<14} {r['count']:>6} {per:>8} {exp:>8} {'/'.join(map(str, r['dlc'])):>4}")
    if ctx.transactions:
        lines += ["", "uds:"]
        for tx in ctx.transactions:
            final = tx.final.describe() if tx.final else "(no final response)"
            lat = f"{tx.latency_ms:6.1f} ms" if tx.latency_ms is not None else "     -   "
            pend = f" +{tx.pending_count}x0x78" if tx.pending_count else ""
            lines.append(f"  t={_rel(ctx, tx.request.src.ts_first):7.3f}  {tx.request.describe():<44} -> {final}  {lat}{pend}")
    lines += ["", f"findings: {len(findings)}"]
    for f in findings:
        where = f"frame {f.frame_index}" if f.frame_index is not None else "         "
        lines.append(f"  [{f.severity:<7}] {f.rule}  {where:>11}  t={_rel(ctx, f.ts):7.3f}  {f.subject}: {f.message}")
    return "\n".join(lines) + "\n"


def render_json(ctx: Context, findings: list[Finding]) -> str:
    return json.dumps({
        "frames": len(ctx.frames), "duration_s": ctx.t_end - ctx.t_start,
        "ids": id_table(ctx),
        "uds": [{"t": _rel(ctx, tx.request.src.ts_first), "request": tx.request.describe(),
                 "final": tx.final.describe() if tx.final else None, "latency_ms": tx.latency_ms,
                 "pending": tx.pending_count} for tx in ctx.transactions],
        "busload": [{"t": _rel(ctx, t), "load": round(l, 4)} for t, l in busload_windows(ctx)],
        "findings": [dict(asdict(f), t=_rel(ctx, f.ts)) for f in findings],
    }, indent=2)


def mermaid_uds(ctx: Context, limit: int = 40) -> str:
    lines = ["sequenceDiagram", "    participant T as Tester", "    participant E as ECU"]
    for tx in ctx.transactions[:limit]:
        lines.append(f"    T->>E: {tx.request.describe()}")
        for r in tx.responses:
            arrow = "-->>" if r.negative else "->>"
            lines.append(f"    E{arrow}T: {r.describe()}")
        if tx.final is None and not tx.request.suppress_positive:
            lines.append("    Note over E: no final response")
    return "\n".join(lines)


def render_md(ctx: Context, findings: list[Finding]) -> str:
    out = ["# CAN log report", "",
           f"{len(ctx.frames)} frames, {len(ctx.by_id)} IDs, {ctx.t_end - ctx.t_start:.2f} s, "
           f"{len(ctx.transactions)} UDS transactions.", "",
           "## Findings", "", "| Sev | Rule | t (s) | Subject | Message |", "|---|---|---|---|---|"]
    for f in findings:
        out.append(f"| {f.severity} | {f.rule} | {_rel(ctx, f.ts):.3f} | {f.subject} | {f.message} |")
    out += ["", "## Messages", "", "| ID | Name | Count | Period (ms) | Expected | DLC | Last decoded |", "|---|---|---|---|---|---|---|"]
    for r in id_table(ctx):
        dec = ", ".join(f"{k}={v:g}" for k, v in r["last_decoded"].items())
        out.append(f"| {r['id']} | {r['name']} | {r['count']} | {r['period_ms'] or '-'} | "
                   f"{r['expected_ms'] or '-'} {r['source']} | {'/'.join(map(str, r['dlc']))} | {dec} |")
    if ctx.transactions:
        out += ["", "## UDS", "", "```mermaid", mermaid_uds(ctx), "```"]
    return "\n".join(out) + "\n"


def busload_svg(ctx: Context, width: int = 720, height: int = 160) -> str:
    pts = busload_windows(ctx)
    if len(pts) < 2:
        return ""
    t0 = ctx.t_start
    span = max(pts[-1][0] - t0, 1e-9)
    ymax = max(max(l for _, l in pts) * 1.2, 0.05)
    x = lambda t: 40 + (t - t0) / span * (width - 60)
    y = lambda v: height - 25 - v / ymax * (height - 40)
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(t):.1f},{y(l):.1f}" for i, (t, l) in enumerate(pts))
    limit_y = y(ctx.busload_limit)
    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px;font:11px system-ui">',
           f'<line x1="40" y1="{y(0):.1f}" x2="{width-20}" y2="{y(0):.1f}" stroke="#999"/>',
           f'<line x1="40" y1="{y(0):.1f}" x2="40" y2="15" stroke="#999"/>',
           f'<text x="4" y="{y(0):.0f}">0%</text><text x="4" y="{y(ymax*0.9):.0f}">{ymax*90:.0f}%</text>']
    if ctx.busload_limit < ymax:
        svg.append(f'<line x1="40" y1="{limit_y:.1f}" x2="{width-20}" y2="{limit_y:.1f}" stroke="#c33" stroke-dasharray="4 3"/>'
                   f'<text x="{width-18}" y="{limit_y+4:.0f}" fill="#c33">limit</text>')
    svg.append(f'<path d="{path}" fill="none" stroke="#1f6feb" stroke-width="1.5"/>')
    svg.append(f'<text x="{width/2:.0f}" y="{height-6}" text-anchor="middle">bus load per second, worst-case stuffing, {ctx.bitrate//1000} kbit/s</text>')
    svg.append("</svg>")
    return "\n".join(svg)


def render_html(ctx: Context, findings: list[Finding], title: str = "CAN log report") -> str:
    e = html.escape
    sev_color = {"ERROR": "#c33", "WARNING": "#b8860b", "INFO": "#1f6feb"}
    rows = "".join(
        f'<tr><td style="color:{sev_color[f.severity]};font-weight:600">{f.severity}</td><td>{f.rule}</td>'
        f'<td>{_rel(ctx, f.ts):.3f}</td><td>{"" if f.frame_index is None else f.frame_index}</td>'
        f'<td>{e(f.subject)}</td><td>{e(f.message)}</td></tr>' for f in findings)
    ids = "".join(
        f'<tr><td><code>{r["id"]}</code></td><td>{e(r["name"])}</td><td>{r["count"]}</td>'
        f'<td>{r["period_ms"] if r["period_ms"] else "-"}</td><td>{r["expected_ms"] or "-"} {r["source"]}</td>'
        f'<td>{"/".join(map(str, r["dlc"]))}</td>'
        f'<td>{e(", ".join(f"{k}={v:g}" for k, v in r["last_decoded"].items()))}</td></tr>' for r in id_table(ctx))
    uds = "".join(
        f'<tr><td>{_rel(ctx, tx.request.src.ts_first):.3f}</td><td>{e(tx.request.describe())}</td>'
        f'<td>{e(tx.final.describe()) if tx.final else "<i>none</i>"}</td>'
        f'<td>{f"{tx.latency_ms:.1f}" if tx.latency_ms is not None else "-"}</td><td>{tx.pending_count or ""}</td></tr>'
        for tx in ctx.transactions)
    counts = {s: sum(1 for f in findings if f.severity == s) for s in ("ERROR", "WARNING", "INFO")}
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title>
<style>body{{font:14px system-ui;margin:2em auto;max-width:960px;padding:0 1em;color:#222}}
table{{border-collapse:collapse;width:100%;margin:1em 0}}td,th{{border:1px solid #ddd;padding:4px 8px;text-align:left;font-size:13px}}
th{{background:#f4f4f4}}code{{font-family:ui-monospace,monospace}}.k{{display:inline-block;margin-right:1.5em}}</style></head><body>
<h1>{e(title)}</h1>
<p><span class="k"><b>{len(ctx.frames)}</b> frames</span><span class="k"><b>{len(ctx.by_id)}</b> IDs</span>
<span class="k"><b>{ctx.t_end - ctx.t_start:.2f}</b> s</span><span class="k"><b>{len(ctx.transactions)}</b> UDS transactions</span>
<span class="k" style="color:#c33"><b>{counts['ERROR']}</b> errors</span><span class="k" style="color:#b8860b"><b>{counts['WARNING']}</b> warnings</span></p>
{busload_svg(ctx)}
<h2>Findings</h2><table><tr><th>Sev</th><th>Rule</th><th>t (s)</th><th>Frame</th><th>Subject</th><th>Message</th></tr>{rows or '<tr><td colspan=6>none</td></tr>'}</table>
<h2>Messages</h2><table><tr><th>ID</th><th>Name</th><th>Count</th><th>Period (ms)</th><th>Expected</th><th>DLC</th><th>Last decoded</th></tr>{ids}</table>
{'<h2>UDS</h2><table><tr><th>t (s)</th><th>Request</th><th>Final response</th><th>Latency (ms)</th><th>0x78</th></tr>' + uds + '</table>' if ctx.transactions else ''}
<p style="color:#888;font-size:12px">cananalyzer — standard library only</p></body></html>
"""


RENDERERS = {"text": render_text, "json": render_json, "md": render_md, "html": render_html,
             "mermaid": lambda ctx, f: mermaid_uds(ctx) + "\n"}

"""A live instrument cluster in the browser. Standard library only.

    python -m vehicle --dashboard            # then open http://localhost:8080

One HTTP server, two endpoints: `/` serves the page, `/events` streams a JSON
snapshot ten times a second over Server-Sent Events. `/state` returns one
snapshot, for tests and for curl. No framework, no websocket library: SSE is
a text/event-stream response that never ends, which http.server can do.
浏览器里的实时仪表。只用标准库。SSE 就是一个永不结束的 text/event-stream 响应，
http.server 做得到，不需要框架。
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import can

from . import busload

RECENT_FRAMES = 24
LOAD_WINDOW_S = 1.0


class DashboardListener(can.Listener):
    """Keeps what the page needs and the cluster does not: the raw frame tail
    and the bits-per-second the bus is carrying."""

    def __init__(self, t0: float, bitrate: int = 500_000):
        self.t0 = t0
        self.bitrate = bitrate
        self.recent: deque[str] = deque(maxlen=RECENT_FRAMES)
        self._bits: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()
        self.total = 0

    def on_message_received(self, msg: can.Message):
        t = time.monotonic() - self.t0
        bits = busload.frame_bits(min(len(msg.data), 8), msg.is_extended_id)
        line = f"{t:9.3f}  {msg.arbitration_id:03X}  [{len(msg.data)}]  {bytes(msg.data).hex(' ').upper()}"
        with self._lock:
            self.recent.append(line)
            self._bits.append((t, bits))
            self.total += 1

    def load(self) -> float:
        now = time.monotonic() - self.t0
        with self._lock:
            while self._bits and now - self._bits[0][0] > LOAD_WINDOW_S:
                self._bits.popleft()
            return sum(b for _, b in self._bits) / (self.bitrate * LOAD_WINDOW_S)

    def tail(self) -> list[str]:
        with self._lock:
            return list(self.recent)


def snapshot(cluster, listener: DashboardListener, senders=None) -> dict:
    st = cluster.state
    now = time.monotonic() - cluster.t0
    messages = []
    for frame_id, rx in cluster.receivers.items():
        d = cluster.db.get_message_by_frame_id(frame_id)
        last = cluster.last_seen.get(frame_id)
        messages.append({
            "name": d.name, "id": f"0x{frame_id:03X}", "cycle_ms": d.cycle_time,
            "age_ms": None if last is None else round((now - last) * 1000),
            "verdict": st.last_verdict.get(d.name, "-"),
            "stats": rx.stats,
            "timed_out": any(name == d.name for _, name in st.timeouts),
        })
    body = st.decoded.get("BODY_STATUS", {})
    engine = st.decoded.get("ENGINE_DATA", {})
    abs_ = st.decoded.get("ABS_DATA", {})
    return {
        "t": round(now, 2),
        "rpm": round(st.engine_rpm),
        "speed": round(st.speed_kmh, 1),
        "throttle": engine.get("ThrottlePos", 0),
        "coolant": engine.get("CoolantTemp", 0),
        "brake": bool(abs_.get("BrakeActive", 0)),
        "turn": st.turn,
        "doors": [bool(body.get(k, 0)) for k in ("DoorFL", "DoorFR", "DoorRL", "DoorRR")],
        "low_beam": bool(body.get("LowBeam", 0)),
        "outside_temp": body.get("OutsideTemp"),
        "messages": messages,
        "e2e_faults": len(st.e2e_events),
        "last_fault": (f"t={st.e2e_events[-1][0]:.2f}s {st.e2e_events[-1][1]}: {st.e2e_events[-1][2]}"
                       if st.e2e_events else ""),
        "unknown_ids": [f"0x{i:X}" for i in sorted(st.unknown_ids)],
        "busload": round(listener.load(), 4),
        "frames_seen": listener.total,
        "sent": {s.message_name: s.sent for s in senders} if senders else {},
        "frames": listener.tail(),
    }


def serve(snapshot_fn, port: int = 8080, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Start serving in a daemon thread; returns the server (use .server_port)."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):   # the vehicle's own output is the log
            pass

        def do_GET(self):
            if self.path == "/":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/state":
                body = json.dumps(snapshot_fn()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(f"data: {json.dumps(snapshot_fn())}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass   # the tab was closed; that is the normal end of an SSE stream
            else:
                self.send_error(404)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="dashboard").start()
    return server


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>can-bus-lab cluster</title>
<style>
:root{--bg:#0f1218;--panel:#181c25;--fg:#e6e6e6;--dim:#7d8590;--ok:#2da44e;--warn:#d29922;--err:#f85149;--acc:#58a6ff}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
header{display:flex;gap:2em;align-items:baseline;padding:10px 20px;border-bottom:1px solid #2a2f3a}
header b{color:var(--acc)}header span{color:var(--dim)}
main{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 20px;max-width:1200px;margin:auto}
.panel{background:var(--panel);border-radius:10px;padding:14px 16px}
.panel h2{margin:0 0 8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.gauges{display:flex;justify-content:space-around;align-items:center;flex-wrap:wrap}
svg.dial{width:260px;height:180px}
.dial text{fill:var(--fg);font-size:13px}.dial .big{font-size:26px;font-weight:600}.dial .unit{fill:var(--dim)}
.dial .tick{stroke:#555;stroke-width:2}.dial .arc{stroke:#2a2f3a;stroke-width:10;fill:none}
.dial .needle{stroke:var(--err);stroke-width:3;stroke-linecap:round;transition:transform .12s linear;transform-origin:130px 140px}
.tell{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:6px}
.tell span{padding:4px 10px;border-radius:6px;background:#22262f;color:var(--dim);border:1px solid #2a2f3a}
.tell span.on{color:#111;background:var(--warn);border-color:var(--warn)}
.tell span.red.on{background:var(--err);border-color:var(--err);color:#fff}
.tell span.green.on{background:var(--ok);border-color:var(--ok);color:#fff}
.car{display:grid;grid-template-columns:1fr 1fr;gap:6px;width:120px;margin:10px auto}
.door{height:36px;border-radius:6px;background:#22262f;border:1px solid #2a2f3a}.door.open{background:var(--err)}
table{width:100%;border-collapse:collapse}td,th{padding:5px 6px;text-align:left;border-bottom:1px solid #2a2f3a;font-size:13px}
th{color:var(--dim);font-weight:500}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:var(--dim)}
.dot.ok,.dot.initial{background:var(--ok)}.dot.crc,.dot.repeated,.dot.wrong_seq,.dot.dlc{background:var(--err)}.dot.lost{background:var(--warn)}
.bar{height:14px;background:#22262f;border-radius:7px;overflow:hidden;margin:6px 0}
.bar i{display:block;height:100%;background:var(--ok);transition:width .2s}.bar i.hi{background:var(--err)}
pre{margin:0;font:12px/1.5 ui-monospace,Menlo,monospace;color:#c9d1d9;white-space:pre;overflow:auto;height:390px}
.stale{color:var(--err)}.fault{color:var(--err);font-size:12px;min-height:1.2em}
@media (max-width:820px){main{grid-template-columns:1fr}}
</style></head><body>
<header><b>can-bus-lab</b><span>virtual vehicle · instrument cluster</span><span id="t">t = 0.00 s</span><span id="conn">connecting…</span></header>
<main>
<section class="panel"><h2>Gauges — what the cluster decoded from the DBC</h2>
<div class="gauges">
 <svg class="dial" id="rpm" viewBox="0 0 260 180"></svg>
 <svg class="dial" id="spd" viewBox="0 0 260 180"></svg>
</div>
<div class="tell">
 <span id="tl">◀ LEFT</span><span id="lb" class="green">LOW BEAM</span><span id="brk" class="red">BRAKE</span><span id="tr">RIGHT ▶</span>
</div>
<div class="car"><div class="door" id="d0"></div><div class="door" id="d1"></div><div class="door" id="d2"></div><div class="door" id="d3"></div></div>
<div class="tell"><span id="cool"></span><span id="thr"></span><span id="ot"></span></div>
</section>
<section class="panel"><h2>Bus — what is actually on the wire</h2>
<div>bus load (worst-case stuffing, 500 kbit/s): <b id="loadv">0%</b></div><div class="bar"><i id="load" style="width:0"></i></div>
<table><thead><tr><th>Message</th><th>ID</th><th>Cycle</th><th>Age</th><th>Last E2E</th><th>ok</th><th>crc</th><th>rep</th><th>lost</th><th>seq</th></tr></thead><tbody id="msgs"></tbody></table>
<div style="margin-top:8px">E2E faults rejected before the gauges: <b id="faults">0</b></div><div class="fault" id="lastfault"></div>
<div id="unk" class="fault"></div>
</section>
<section class="panel" style="grid-column:1/-1"><h2>Frames — the last 24, candump style</h2><pre id="frames"></pre></section>
</main>
<script>
function dial(id,label,unit,max,step){const s=document.getElementById(id);const cx=130,cy=140,r=105;let h='';
 const a=v=>Math.PI*(1+v/max);const P=(v,rr)=>[cx+rr*Math.cos(a(v)),cy+rr*Math.sin(a(v))];
 h+=`<path class="arc" d="M ${P(0,r)} A ${r} ${r} 0 0 1 ${P(max,r)}"/>`;
 for(let v=0;v<=max;v+=step){const [x1,y1]=P(v,r-8),[x2,y2]=P(v,r+2),[tx,ty]=P(v,r-24);h+=`<line class="tick" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/><text x="${tx}" y="${ty+4}" text-anchor="middle" style="font-size:10px;fill:#7d8590">${v}</text>`}
 h+=`<line class="needle" id="${id}n" x1="${cx}" y1="${cy}" x2="${cx-r+14}" y2="${cy}"/><circle cx="${cx}" cy="${cy}" r="6" fill="#f85149"/>`;
 h+=`<text class="big" id="${id}v" x="${cx}" y="${cy+32}" text-anchor="middle">0</text><text class="unit" x="${cx}" y="${cy+50}" text-anchor="middle">${label} · ${unit}</text>`;
 s.innerHTML=h;return v=>{v=Math.max(0,Math.min(max,v));document.getElementById(id+'n').style.transform=`rotate(${180*v/max}deg)`;document.getElementById(id+'v').textContent=Math.round(v)}}
const setRpm=dial('rpm','engine','rpm',8000,1000),setSpd=dial('spd','vehicle','km/h',200,20);
const $=id=>document.getElementById(id);let blink=false;setInterval(()=>blink=!blink,400);
function render(s){$('t').textContent=`t = ${s.t.toFixed(2)} s`;setRpm(s.rpm);setSpd(s.speed);
 $('tl').classList.toggle('on',blink&&(s.turn==='Left'||s.turn==='Hazard'));$('tr').classList.toggle('on',blink&&(s.turn==='Right'||s.turn==='Hazard'));
 $('lb').classList.toggle('on',s.low_beam);$('brk').classList.toggle('on',s.brake);
 s.doors.forEach((d,i)=>$('d'+i).classList.toggle('open',d));
 $('cool').textContent=`coolant ${s.coolant} °C`;$('thr').textContent=`throttle ${Number(s.throttle).toFixed(0)} %`;$('ot').textContent=s.outside_temp==null?'':`outside ${s.outside_temp} °C`;
 const pct=Math.round(s.busload*100);$('loadv').textContent=pct+'%';const b=$('load');b.style.width=Math.min(100,pct)+'%';b.classList.toggle('hi',pct>70);
 $('msgs').innerHTML=s.messages.map(m=>{const stale=m.age_ms!=null&&m.age_ms>3*m.cycle_ms;return `<tr><td>${m.name}</td><td><code>${m.id}</code></td><td>${m.cycle_ms} ms</td><td class="${stale?'stale':''}">${m.age_ms==null?'never':m.age_ms+' ms'}${m.timed_out?' TIMEOUT':''}</td><td><i class="dot ${m.verdict}"></i>${m.verdict}</td><td>${m.stats.ok}</td><td>${m.stats.crc}</td><td>${m.stats.repeated}</td><td>${m.stats.lost}</td><td>${m.stats.wrong_seq}</td></tr>`}).join('');
 $('faults').textContent=s.e2e_faults;$('lastfault').textContent=s.last_fault;$('unk').textContent=s.unknown_ids.length?'IDs not in DBC: '+s.unknown_ids.join(', '):'';
 $('frames').textContent=s.frames.join('\n')}
const es=new EventSource('/events');es.onmessage=e=>render(JSON.parse(e.data));
es.onopen=()=>{$('conn').textContent='live';$('conn').style.color='#2da44e'};es.onerror=()=>{$('conn').textContent='vehicle stopped';$('conn').style.color='#f85149'};
</script></body></html>
"""

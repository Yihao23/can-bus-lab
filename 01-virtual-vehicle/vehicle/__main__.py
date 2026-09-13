"""Run the virtual vehicle.

    python -m vehicle                                  # vcan0, 10 s
    python -m vehicle --channel virtual --duration 5   # no kernel module needed
    python -m vehicle --fault stuck-counter --log out.log
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

import can

from . import busload, dashboard
from .ecus import AbsEcu, BcmEcu, ClusterEcu, EngineEcu, Faults, load_db


def open_bus(args) -> can.BusABC:
    if args.channel == "virtual":
        return can.Bus(interface="virtual", channel="lab")
    return can.Bus(interface=args.interface, channel=args.channel)


def parse_faults(specs: list[str]) -> Faults:
    f = Faults()
    for spec in specs:
        name, _, value = spec.partition("=")
        if name == "stuck-counter":
            f.stuck_counter = True
        elif name == "bad-crc":
            f.bad_crc_every = int(value or 10)
        elif name == "engine-stop":
            f.engine_stop_after = float(value or 3.0)
        elif name == "jitter":
            f.jitter_ms = float(value or 10.0)
        elif name == "drop-abs":
            f.drop_abs = float(value or 0.1)
        elif name == "wrong-dlc":
            f.wrong_dlc = True
        else:
            sys.exit(f"unknown fault {name!r}; see --help")
    return f


def main(argv=None):
    p = argparse.ArgumentParser(description="three-ECU virtual vehicle on CAN")
    p.add_argument("--interface", default="socketcan")
    p.add_argument("--channel", default="vcan0", help="'virtual' for the in-process bus")
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--bitrate", type=int, default=500_000, help="only used for the bus-load estimate")
    p.add_argument("--log", help="write a candump-format log (.log) of everything on the bus")
    p.add_argument("--dashboard", nargs="?", const=8080, type=int, metavar="PORT",
                   help="serve a live instrument cluster at http://localhost:PORT (default 8080)")
    p.add_argument("--fault", action="append", default=[], metavar="NAME[=VALUE]",
                   help="stuck-counter | bad-crc[=N] | engine-stop[=SEC] | jitter[=MS] | drop-abs[=FRACTION] | wrong-dlc")
    args = p.parse_args(argv)

    db = load_db()
    faults = parse_faults(args.fault)
    cyclic = [busload.CyclicMessage(m.name, m.length, m.cycle_time) for m in db.messages if m.cycle_time]
    load = busload.bus_load(cyclic, args.bitrate)
    print(f"bus      {len(cyclic)} cyclic messages, worst-case load {load*100:.1f}% at {args.bitrate//1000} kbit/s")

    stop = threading.Event()
    t0 = time.monotonic()
    buses = [open_bus(args) for _ in range(4)]
    senders = [EngineEcu(buses[0], db, faults, t0, stop),
               AbsEcu(buses[1], db, faults, t0, stop),
               BcmEcu(buses[2], db, faults, t0, stop)]
    cluster = ClusterEcu(db, t0)
    listeners: list[can.Listener] = [cluster]
    if args.log:
        listeners.append(can.Logger(args.log))
    if args.dashboard is not None:
        dash = dashboard.DashboardListener(t0, args.bitrate)
        listeners.append(dash)
        server = dashboard.serve(lambda: dashboard.snapshot(cluster, dash, senders), args.dashboard)
        print(f"dash     open http://localhost:{server.server_port}/  (Ctrl-C stops the vehicle)")
    notifier = can.Notifier(buses[3], listeners)

    for s in senders:
        s.start()
    try:
        while time.monotonic() - t0 < args.duration:
            time.sleep(0.05)
            cluster.check_timeouts(time.monotonic() - t0)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for s in senders:
            s.join(timeout=1)
        notifier.stop()
        for b in buses:
            b.shutdown()

    st = cluster.state
    print(f"summary  sent engine={senders[0].sent} abs={senders[1].sent} bcm={senders[2].sent}; "
          f"cluster received {st.frames}")
    for rx_id, rx in cluster.receivers.items():
        print(f"e2e      0x{rx_id:03X} {rx.stats}")
    for t, name, what in st.e2e_events[:10]:
        print(f"fault    t={t:6.3f}s {name}: {what}")
    if len(st.e2e_events) > 10:
        print(f"fault    ... {len(st.e2e_events) - 10} more")
    for t, name in st.timeouts:
        print(f"timeout  t={t:6.3f}s {name} stopped arriving")
    if st.unknown_ids:
        print("unknown  ids not in DBC: " + ", ".join(f"0x{i:X}" for i in sorted(st.unknown_ids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

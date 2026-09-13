# 01 · Virtual Vehicle: three ECUs on a CAN bus
# 01 · 虚拟整车: 总线上的三个 ECU

**Goal / 目标** — Write a DBC from scratch, put three ECUs on a bus that send
real cyclic frames from it, protect them with an alive counter and CRC, and
have a fourth ECU catch every way the first three can lie.
从零写一份 DBC，让三个 ECU 按它周期发真实的帧，用计数器和 CRC 保护，
再让第四个 ECU 抓出前三个所有可能的"撒谎"方式。

**Why this matters / 为什么重要** — Every automotive interview asks about the
CAN frame, arbitration and the DBC. Most candidates have read about them. After
this project you have *encoded* a Motorola signal by hand, *computed* a bus
load, and *watched* a CRC failure get rejected before it reaches a gauge.
每场车企面试都会问 CAN 帧、仲裁和 DBC。大多数候选人只是读过。做完这个项目，
你亲手编码过 Motorola 字节序的信号、算过总线负载、亲眼看过一次 CRC 错误在
到达仪表之前就被拒掉。

---

## Quick start / 快速开始

```bash
cd 01-virtual-vehicle
source ../.venv/bin/activate          # created by ../setup/bootstrap.sh
pip install -r requirements.txt

# no kernel module, no sudo: python-can's in-process virtual bus
# 不需要内核模块和 sudo: python-can 进程内虚拟总线
python -m vehicle --channel virtual --duration 5

# the real thing: a Linux vcan interface that candump and Wireshark can see
# 真正的玩法: Linux vcan 接口，candump 和 Wireshark 都能看见
sudo ../setup/vcan-up.sh
python -m vehicle --duration 30 &
candump -td -c vcan0                  # terminal 2

# the same, with a live instrument cluster in the browser
# 同上，外加浏览器里的实时仪表
python -m vehicle --channel virtual --duration 120 --dashboard --fault bad-crc=40
# then open http://localhost:8080

python -m unittest discover -s tests -v     # 31 tests, no network needed
```

---

## What you should see / 你应该看到什么

```
bus      3 cyclic messages, worst-case load 3.0% at 500 kbit/s
cluster  t=  0.50s  rpm=  1318  speed=  3.6 km/h  turn=Off     frames=56   e2e_faults=0
cluster  t=  1.00s  rpm=  1518  speed=  7.5 km/h  turn=Off     frames=113  e2e_faults=0
summary  sent engine=101 abs=101 bcm=21; cluster received 223
e2e      0x100 {'ok': 101, 'initial': 0, 'crc': 0, 'repeated': 0, 'lost': 0, 'wrong_seq': 0}
```

And in `candump` — this is what the DBC turns into on the wire:
在 `candump` 里 —— DBC 到了线上就是这个样子:

```
 (000.000000)  vcan0  100   [8]  24 12 70 3C 01 00 00 33
 (000.000470)  vcan0  1A0   [8]  02 00 00 00 00 00 00 74
 (000.000237)  vcan0  300   [8]  02 25 00 00 00 00 00 40
```

`24 12` is `EngineSpeed` = 0x1224 × 0.25 = 1161 rpm, Intel byte order, low
byte first. Byte 6 low nibble is the alive counter, byte 7 the CRC.
`24 12` 就是 `EngineSpeed` = 0x1224 × 0.25 = 1161 rpm，Intel 字节序，低字节在前。
第 6 字节低半字节是计数器，第 7 字节是 CRC。

---

## The dashboard / 仪表页

![Live cluster with a CRC fault being rejected](screenshots/dashboard.jpg)

`--dashboard` serves this at `localhost:8080`. Left: what the cluster
*decoded* — needles, indicators, doors, the Motorola `OutsideTemp`. Right:
what is *on the wire* — bus load, per-message age and E2E verdict with
counters, and the last 24 frames candump-style. Standard library only:
`http.server` plus a Server-Sent Events stream, no framework.
左边是仪表**解码出来**的东西，右边是**线上**实际有的东西。只用标准库:
`http.server` 加一条 SSE 流，没有框架。

The screenshot above was taken with `--fault bad-crc=40 --fault drop-abs=0.03`.
Two things to notice, and to be able to explain:
截图开着 `--fault bad-crc=40 --fault drop-abs=0.03`。两件要能解释的事:

1. **`ENGINE_DATA` shows `crc` with 64 rejected, yet the needle keeps
   moving.** The cluster drops the bad frame and keeps the last good value; the
   next good frame 20 ms later updates it. That is the "fail-safe" behaviour
   from decision 3 below.
   `ENGINE_DATA` 显示 `crc`、拒了 64 帧，但指针照常走: 仪表丢掉坏帧、保留上一个好值，
   20 ms 后的下一帧更新它。
2. **`ABS_DATA` shows `lost = 0` in this screenshot although 3 % of its frames
   were dropped.** The image was captured before the day-3 counter check was
   written: with the placeholder `check()`, every frame with a valid CRC counted
   as `ok`. The check is now implemented, so `--fault drop-abs` makes the `lost`
   column climb — re-run with `--dashboard` and watch it. The dashboard is the
   test you can see.
   截图里 `ABS_DATA` 丢了 3% 的帧却显示 `lost = 0`: 那是第 3 天计数器检查写好之前截的。
   现在检查已实现，`--fault drop-abs` 会让 `lost` 列往上涨，重跑 `--dashboard` 就能看到。

The `Age` column turns red past 3 × cycle time, and `TIMEOUT` appears next
to it once `check_timeouts()` (day 4) reports one. Try `--fault engine-stop=5`
and watch the rpm needle: does it hold or drop? Which is right?
`Age` 列超过 3 倍周期变红；`check_timeouts()` 实现后会出现 `TIMEOUT`。
试 `--fault engine-stop=5` 看转速指针: 是停住还是归零? 哪个才对?

---

## Break it on purpose / 故意搞坏它

Each `--fault` is one thing that goes wrong on real buses. Run each, watch
what the cluster reports, and be able to say what would happen in a car.
每个 `--fault` 都是真车上会出的一种问题。逐个跑，看仪表报什么，
并能说出在真车上会发生什么。

| Fault | What it simulates / 模拟什么 | Cluster sees / 仪表看到 |
|---|---|---|
| `stuck-counter` | Engine ECU software hung, hardware timer keeps re-sending the last buffer / 发动机 ECU 软件卡死，硬件定时器仍在重发最后一份缓冲 | `repeated` (once you write the check) |
| `bad-crc=10` | Corruption between application and CAN controller — memory, DMA, a gateway rewriting bytes / 应用层与 CAN 控制器之间的损坏 | `crc`, frame never reaches the gauge |
| `engine-stop=3` | Node dropped off the bus: bus-off, unplugged, reset loop / 节点掉线: bus-off、拔线、复位循环 | `timeout` (once you write the check) |
| `jitter=10` | Overloaded scheduler, cycle time 20 ± 10 ms / 调度超载 | nothing here — project 04 catches it in the log |
| `drop-abs=0.1` | 10 % frame loss: bad connector, marginal termination / 10% 丢帧: 接插件不良、终端电阻不对 | `lost` |
| `wrong-dlc` | ECU with the wrong DBC version / ECU 刷了错的 DBC 版本 | `dlc 6 != 8` |

Every fault also produces a log you can hand to project 04:
每个故障都能顺手产出一份给项目 04 用的日志:

```bash
python -m vehicle --channel virtual --duration 5 --fault bad-crc=10 --log ../04-can-log-analyzer/samples/mine.log
```

---

## Architecture / 架构

```
dbc/lab_vehicle.dbc      the contract: IDs, signals, byte order, cycle times, E2E DataIDs
        │
        ▼ cantools
vehicle/ecus.py          EngineEcu ─┐
                         AbsEcu    ─┼─► bus (vcan0 or in-process virtual) ─► ClusterEcu
                         BcmEcu    ─┘       │                                    │
vehicle/e2e.py           protect() ─────────┘                                    └── E2EReceiver.check()
vehicle/busload.py       frame_bits(), bus_load()  — the arithmetic, not a simulation
vehicle/dashboard.py     DashboardListener (frame tail + live load) ─► snapshot() ─► /events (SSE) ─► browser
```

**Three design decisions to defend in the interview / 面试里要能辩护的三个决策:**

1. **Each ECU has its own bus handle and its own thread.** A shared handle would
   serialise them and hide exactly the timing you want to study.
   每个 ECU 自己一个总线句柄、一个线程。共用句柄会把它们串行化，恰好掩盖你想研究的时序。
2. **The cluster is a `Listener`, not a polling thread.** A receive path is
   event-driven; a timeout, however, cannot be detected from a receive
   callback — a message that stopped arriving never calls you. That is why
   `check_timeouts()` runs from the main loop.
   仪表是 `Listener` 而不是轮询线程。接收路径是事件驱动的；但超时不可能在收包回调里检测 ——
   不再到达的报文永远不会调用你。所以 `check_timeouts()` 从主循环跑。
3. **A frame that fails E2E never reaches the gauge.** Showing a stale speed is
   worse than showing nothing. ISO 26262 calls this "fail-safe state".
   E2E 失败的帧永远到不了仪表。显示一个过期的车速比什么都不显示更糟。

---

## What vcan cannot show you / vcan 给不了你的

Be honest about this in the interview; it is the "limitation" third of
claim → evidence → limitation.
面试里要主动说，这是"主张 → 证据 → 局限"的第三段。

- **No arbitration.** vcan is a kernel queue. Two frames sent at once do not
  fight; they queue. So `0x100` winning over `0x300` is something you can
  *explain* (lower ID, dominant bit wins) but not *observe* here.
  没有仲裁。两帧同时发不会竞争，只会排队。
- **No bit stuffing, no error frames, no TEC/REC, no bus-off.** `busload.py`
  computes the worst-case stuffing arithmetically; nothing here transmits a
  stuff bit.
- **No termination, no physical layer.** The only way to see any of the above
  is real hardware — see the optional project 05 in the root README.

---

## Step by step / 分步推进

### Day 2 — read the wire / 读懂线上的东西
- [ ] Run with `--channel virtual`. Read the printed frames against the DBC by
  hand: pick one `100#...` line and decode `EngineSpeed` with a calculator.
- [ ] Do the same for a `300#...` line: `OutsideTemp` is Motorola. Write down
  why the start bit in the DBC (15) is the MSB and not the LSB.
- [ ] `cantools decode dbc/lab_vehicle.dbc < your.log` — check your arithmetic.

### Day 3 — E2E receiver check / E2E 接收端检查  ✅ done
- [x] Uncomment the five tests in `tests/test_e2e.py`. Run them. They fail.
- [x] Implement `E2EReceiver.check()` in `vehicle/e2e.py`.
- [x] `--fault stuck-counter` now reports `repeated`; `--fault drop-abs=0.2`
  reports `lost`.

**`MaxDeltaCounter = 3`, and why not 1 or 14.** A real bus loses the odd frame
to a busy moment or a marginal connector; tolerating a gap of 1–2 (delta 2–3)
as `lost` — a warning, not an error — keeps those from crying wolf. But a big
jump is not "a few frames dropped", it is a node that reset, a replay, or a
scrambled counter, so past the threshold it becomes `wrong_seq` (error). 1
would flag every normal hiccup; 14 would call a total dropout "just some loss".
真实总线偶尔掉一两帧很正常，容忍 delta 2–3 判 `lost`(警告)不误报；跳得多则是重启/重放/
乱序，超阈值判 `wrong_seq`(错误)。取 1 会把正常抖动全报，取 14 会把彻底掉线当成小丢帧。

**A CRC error and a lost frame were being counted twice — the design call.**
A CRC-rejected frame is dropped before its counter is read, so it does not
advance `last_counter`; the next good frame then looks like it skipped a count
and reads as `lost`, on top of the `crc` already reported. With
`--fault bad-crc=2` (every other frame bad) *every* good frame lands on that
gap, so `ok` never happens. Decision: keep it simple — the test uses
`bad-crc=3` so two good frames still arrive back to back and produce `ok`, and
`lost` after a corrupted frame is accepted as "one frame's data did not make
it, however it failed". The stricter alternative — track how many CRC-rejects
sat between two good frames and subtract them, so `counter=2` after one drop
reads `ok` — is a real improvement left as an exercise; call it `pending_crc`.
坏 CRC 的帧在读 counter 前就被丢，不推进 `last_counter`，下一个好帧看着像跳号被判 `lost`,
和已报的 `crc` 重复计一次。`bad-crc=2` 时每个好帧都落在缺口上，永远出不了 `ok`。决定: 从简,
测试用 `bad-crc=3`，接受"坏帧后判 lost"。更严谨的做法(数两个好帧间有几个坏帧再减掉，
让丢一帧后 `counter=2` 判 `ok`)留作练习，叫它 `pending_crc`。

### Day 4 — timeouts / 超时
- [x] Implement `ClusterEcu.check_timeouts()`, with a test using
  `Faults(engine_stop_after=0.2)`. Detection and the report-once logic are in:
  a message silent for more than 3× its cycle is recorded once, cleared to
  report again when it comes back. `--fault engine-stop=2` now prints
  `timeout t=2.064s ENGINE_DATA stopped arriving`.
- [ ] **Still yours — the gauge decision.** When a message times out, what
  should its gauge show? The default holds the last value; the commented block
  in `check_timeouts()` zeroes it. Neither is obviously safe: a held speed
  looks like nothing changed, a zeroed speed looks like the car stopped. Pick
  one and write why here: ______________________
- [ ] Add a J1939-style 29-bit message to the DBC (PGN 0xFEF1 CCVS, wheel-based
  speed) and a fourth sender for it. `busload.frame_bits(extended=True)` is
  already waiting.

- **Commit:** tests green, and they were red first.

---

## Verified / 已验证

| What | Status |
|---|---|
| `python -m unittest discover -s tests` | ✅ 31 passed (2026-09-13, python-can 4.6.1, cantools 44.0.0) — includes the day-3 receiver check and the day-4 timeout detection |
| `python -m vehicle --channel virtual` healthy + all six faults | ✅ run, output above is real |
| `--dashboard` in Chrome | ✅ run; `screenshots/dashboard.jpg` is that session at t = 51 s |
| `python -m vehicle` on `vcan0` + `candump -td vcan0` | ✅ run (2026-09-13, can-utils 2023.03); `/proc/net/can/rcvlist_all` showed the four sockets |
| `cansend vcan0 100#0000000000000000` while running | ✅ the cluster rejected it: `crc: 1`, `fault t=1.913s ENGINE_DATA: crc`; `cansend vcan0 555#CAFE` → `unknown ids not in DBC: 0x555` |
| Wireshark on `vcan0` | ⬜ not yet run (tshark not installed) |

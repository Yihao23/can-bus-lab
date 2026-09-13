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

python -m unittest discover -s tests -v     # 20 tests, no network needed
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

### Day 3 — E2E receiver check / E2E 接收端检查
- [ ] Uncomment the five tests in `tests/test_e2e.py`. Run them. They fail.
- [ ] Implement `E2EReceiver.check()` in `vehicle/e2e.py`. Pick `MaxDeltaCounter`
  and write here why: ______________________
- [ ] `--fault stuck-counter` now reports `repeated`; `--fault drop-abs=0.2`
  reports `lost`.

### Day 4 — timeouts / 超时
- [ ] Implement `ClusterEcu.check_timeouts()`. Write a test that uses
  `Faults(engine_stop_after=0.2)`.
- [ ] Answer: when `ABS_DATA` times out, should the speedometer hold the last
  value or drop to zero? Answer: ______________________
- [ ] Add a J1939-style 29-bit message to the DBC (PGN 0xFEF1 CCVS, wheel-based
  speed) and a fourth sender for it. `busload.frame_bits(extended=True)` is
  already waiting.

- **Commit:** tests green, and they were red first.

---

## Verified / 已验证

| What | Status |
|---|---|
| `python -m unittest discover -s tests` | ✅ 20 passed (2026-09-13, python-can 4.6.1, cantools 44.0.0) |
| `python -m vehicle --channel virtual` healthy + all six faults | ✅ run, output above is real |
| `python -m vehicle` on `vcan0` + `candump` | ⬜ not yet run on this machine — needs `can-utils` and `setup/vcan-up.sh` |
| Wireshark on `vcan0` | ⬜ not yet run |

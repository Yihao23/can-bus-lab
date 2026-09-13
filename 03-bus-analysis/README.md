# 03 · Bus Analysis: reading a bus you did not build
# 03 · 总线分析: 读一条不是你搭的总线

**Goal / 目标** — Capture two buses you do not know — ICSim's and uds-server's —
find which ID carries the speed, which bit is the left indicator, which DIDs
the ECU answers, and write it up.
抓两条你不认识的总线 —— ICSim 和 uds-server 的 —— 找出哪个 ID 载着车速、
哪一位是左转向灯、ECU 回答哪些 DID，然后写成报告。

**Why / 为什么** — Projects 01 and 02 prove you can build. This proves you can
walk up to a harness with a laptop and come back with a DBC. That is the
daily job in vehicle integration, test, and diagnostics.
项目 01 和 02 证明你会造。这个证明你能拎着笔记本走到线束前，回来时手里有一份 DBC。
这才是整车集成、测试、诊断岗每天在做的事。

⚠️ **This project has almost no code of its own.** `tools/idstat.py` is 50
lines. The deliverable is `report/REPORT-01.md`.
⚠️ **这个项目几乎没有自己的代码。** 交付物是 `report/REPORT-01.md`。

---

## Contents / 内容

| Path | What |
|---|---|
| `setup/run-targets.md` | Bring up ICSim, uds-server, caringcaribou on `vcan0` / 把三个靶子跑起来 |
| `setup/capture.sh` | One command: `.log` + `.pcap` + per-ID stats / 一条命令三份产物 |
| `tools/idstat.py` | The first thing you run on an unknown log / 拿到陌生日志第一个跑的东西 |
| `captures/` | Your captures. Only `.md` is committed by default / 你的抓包，默认只提交 `.md` |
| `report/REPORT-TEMPLATE.md` | ⭐ The deliverable. Fill it in. / ⭐ 交付物，把它填满 |

---

## The method / 方法

Reverse engineering a CAN bus is not magic; it is four moves, in order.
逆向一条 CAN 总线不是魔法，是按顺序的四步。

1. **Count.** `idstat.py`: which IDs, how often, which bytes change. Cyclic
   with stable period and changing bytes = sensor data. Cyclic with nothing
   changing = status/heartbeat. Aperiodic = event (a button).
   **数。** 周期稳定、字节变化 = 传感器数据；周期稳定、没有变化 = 状态/心跳；非周期 = 事件。
2. **Correlate.** Do one thing (accelerate, open a door) and diff the bus
   before and after. `candump vcan0 | grep 244` while you press the key.
   **关联。** 只做一件事，对比前后。
3. **Hypothesise a signal.** Start bit, length, byte order, factor. Then
   *predict* the next value and check. Speed is usually 16 bit; a door is 1 bit.
   **假设一个信号，然后预测下一个值来验证。**
4. **Write the DBC line and prove it.** `cantools decode your.dbc < your.log`
   must produce numbers that match what you did to the car.
   **写下 DBC 行并证明它。**

For diagnostics the moves are the same with different tools: `caringcaribou
uds discovery` counts, `services` correlates, `dump_dids` hypothesises.
诊断也是同样的四步，换工具而已。

---

## Two facts to have ready / 两个要随时能说的事实

1. **Wireshark understands SocketCAN natively** (link type `LINKTYPE_CAN_SOCKETCAN`),
   and can decode ISO-TP and UDS via *Decode As*. It cannot apply a DBC; for
   that use `cantools decode` or SavvyCAN.
   Wireshark 原生认 SocketCAN，通过 Decode As 能解 ISO-TP 和 UDS，但不认 DBC。
2. **`candump -L` and `python-can`'s `Logger` write the same format**, so a log
   from a real interface and a log from project 01 are interchangeable for
   project 04. That is the reason project 04 reads exactly this format.
   `candump -L` 和 python-can 的 Logger 格式相同，真接口的日志和项目 01 的日志
   对项目 04 来说可以互换。

---

## Step by step / 分步推进

### Day 8 — tools on a known bus / 在熟悉的总线上学工具
- [ ] `setup/vcan-up.sh`, then project 01 for 60 s, then `setup/capture.sh known 30`.
- [ ] Read the `.idstat`. Do the periods match the DBC's `GenMsgCycleTime`?
- [ ] Open the `.pcap` in Wireshark. Filter `can.id == 0x100`. Add a column for
  `can.data`.
- [ ] `cansend vcan0 100#0000000000000000` while project 01 runs. What does the
  cluster report? (Hint: `e2e`.) ______________________

### Day 9 — ICSim, blind / ICSim，盲做
- [ ] `./icsim -r 1234 vcan0`, `./controls -r 1234 vcan0`. Capture 60 s while
  doing *one thing at a time* and writing down the timestamps.
- [ ] Fill in REPORT §2–3: the ID for speed, doors, indicators; the DBC lines.
- [ ] `cansend` a frame that puts the speedometer at exactly 88 mph. Screenshot.

### Day 10 — uds-server, blind / uds-server，盲做
- [ ] `caringcaribou uds discovery`, `services`, `dump_dids`. Fill in REPORT §4.
- [ ] Try project 02's tester against it. Explain each failure in REPORT §5.

- **Commit:** `report/REPORT-01.md`, the `.idstat` files, one screenshot.

---

## Verified / 已验证

| What | Status |
|---|---|
| `tools/idstat.py` on project 01's log | ✅ run on `04-can-log-analyzer/samples/healthy.log` |
| `setup/capture.sh` | ⬜ not yet run — needs `can-utils` and `vcan0` |
| ICSim, uds-server, caringcaribou | ⬜ not yet installed on this machine |
| `report/REPORT-01.md` | ⬜ template only |

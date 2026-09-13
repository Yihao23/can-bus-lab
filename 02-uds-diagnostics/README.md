# 02 · UDS Diagnostics: an ECU you can interrogate
# 02 · UDS 诊断: 一台可以被"审问"的 ECU

**Goal / 目标** — Implement the diagnostic side of the engine ECU from project 01:
ISO 14229 (UDS) over ISO 15765-2 (ISO-TP) over CAN. Sessions, security access,
DIDs, DTCs, negative response codes, the S3 timer, and the `0x78` dance.
Then talk to it with a real tester library.
实现项目 01 发动机 ECU 的诊断面: CAN 之上跑 ISO-TP，再之上跑 UDS。会话、安全访问、
DID、DTC、否定响应码、S3 定时器和 `0x78` 那套。然后用真正的诊断仪库和它对话。

**Why this matters / 为什么重要** — "Walk me through a UDS session" and
"what is ISO-TP for" are the second most common CAN interview pair after
arbitration. Here you have written the server, so you can answer from the
side that has to *enforce* the rules, not just follow them.
"讲一遍 UDS 会话"和"ISO-TP 是干什么的"是仅次于仲裁的第二对高频面试题。
你写的是服务端，能从"必须执行规则"的一侧回答，而不只是"遵守规则"的一侧。

---

## Quick start / 快速开始

```bash
cd 02-uds-diagnostics && source ../.venv/bin/activate

# no vcan needed: ECU and tester in one process on the virtual bus
# 不需要 vcan: ECU 和诊断仪在同一进程、虚拟总线上
python -m tester --channel virtual

# the real thing, two terminals on vcan0
python -m ecu -v                 # terminal 1
python -m tester                 # terminal 2
candump vcan0                    # terminal 3 — watch the ISO-TP frames

# kernel ISO-TP from can-utils, no Python on the tester side at all:
# 用 can-utils 的内核 ISO-TP，诊断仪这边一行 Python 都不要:
echo "22 F1 90" | isotpsend -s 7E0 -d 7E8 vcan0 & isotprecv -s 7E0 -d 7E8 vcan0

python -m unittest discover -s tests -v    # 49 tests, ~2 s
```

---

## What you should see / 你应该看到什么

```
tester  read VIN in default session        OK   WCANLAB0000000001
tester  read live engine speed (raw)       OK   3400
tester  read secured DID while locked      NRC  0x33 SecurityAccessDenied
tester  security access in default session NRC  0x7F ServiceNotSupportedInActiveSession
tester  enter extended session             OK   3
tester  security access (seed/key)         OK   True
tester  read secured DID now               OK   CAL-2026-09-A
tester  read three DIDs at once            OK   {61831: 'CANLAB-ENG-0001', 61836: 'SN000042', 61845: '1.0.3'}
tester  read unknown DID                   NRC  0x31 RequestOutOfRange
tester  read slow DID (expect 0x78 first)  OK   57005
tester  count DTCs status mask 0x09        OK   2
tester  list DTCs status mask 0xFF         OK   [('011F00', 9), ('030100', 4), ('C07300', 8)]
tester  tester present                     OK   True
tester  ECU reset while engine runs        NRC  0x22 ConditionsNotCorrect
```

Every `NRC` line above is *correct behaviour*. The script provokes them on
purpose. Being able to say why each one is the right code is the interview.
上面每一行 `NRC` 都是**正确行为**，脚本故意触发的。能说出每个码为什么对，就是面试本身。

And on the wire, reading the VIN — one request, a three-frame answer:
线上读 VIN 的样子 —— 一个请求，三帧回答:

```
7E0  03 22 F1 90 AA AA AA AA     SF, 3 bytes: ReadDataByIdentifier F190
7E8  10 14 62 F1 90 57 43 41     FF, total 0x14 = 20 bytes, first 6 of them
7E0  30 08 00 AA AA AA AA AA     FC: ClearToSend, block size 8, STmin 0
7E8  21 4E 4C 41 42 30 30 30     CF #1
7E8  22 30 30 30 30 30 30 31     CF #2
```

`AA` is padding. The first nibble of byte 0 is the ISO-TP frame type; that is
the whole transport protocol in one byte.
`AA` 是填充。第 0 字节高半字节是 ISO-TP 帧类型 —— 整个传输协议就在这一个字节里。

---

## The rules the server enforces / 服务端执行的规则

| Situation | NRC | Why this one |
|---|---|---|
| Unknown SID | `0x11` serviceNotSupported | The ECU has never heard of it |
| SecurityAccess / ECUReset in default session | `0x7F` serviceNotSupportedInActiveSession | Known service, wrong session — not `0x11` |
| Default → programming directly | `0x22` conditionsNotCorrect | This OEM requires extended first |
| Secured DID while locked | `0x33` securityAccessDenied | |
| Wrong key | `0x35` invalidKey, and the seed is void | One seed, one try; otherwise brute force is free |
| Key without a seed | `0x24` requestSequenceError | |
| Multi-DID read, *some* unknown | positive, unknown ones skipped | ISO 14229 §11.2.5.2 — only *all* unknown is `0x31` |
| ECUReset while engine turns | `0x22` conditionsNotCorrect | A running engine controller does not reset |
| Slow DID | `0x78` then the answer | Tester switches from P2 (50 ms) to P2\* (5 s) |
| No TesterPresent for S3 = 5 s | silently back to default, locked | The tester unplugged; the ECU must not stay open |

**Three things to be able to say / 三件要能说出口的事:**

1. **`0x78` is not an error.** It is "I heard you, keep waiting, and use the
   longer timeout". udsoncan handles it transparently; `candump` shows it.
   `0x78` 不是错误，是"收到，接着等，改用长超时"。
2. **Any session change locks the ECU.** Otherwise: unlock in extended, drop
   to default, come back, still unlocked. `_enter_session()` clears both the
   unlock flag and any outstanding seed.
   任何会话切换都重新上锁，否则解锁后切默认再切回来还是开着的。
3. **The tester needs the DID table to decode a multi-DID reply.** There is
   no delimiter on the wire. That is why `client.py` configures fixed lengths,
   and why a workshop tool without the OEM's ODX file cannot read your ECU.
   诊断仪要有 DID 表才能拆多 DID 响应，线上没有分隔符。所以没有 OEM 的 ODX 文件，
   通用诊断仪读不了你的 ECU。

---

## Architecture / 架构

```
tester/client.py      udsoncan Client ── PythonIsoTpConnection ── can-isotp stack ─┐
                                                                                    │  CAN (vcan0 | virtual)
ecu/transport.py      UdsEcuOnCan thread ── can-isotp stack ───────────────────────┘
        │  bytes in / list[bytes] out
        ▼
ecu/uds_server.py     UdsServer.handle(request, now) — pure logic, no I/O, 100 % unit-testable
```

**The design decision to defend / 要辩护的设计决策:** `UdsServer` takes
`now` as a parameter instead of calling `time.monotonic()`. That is what
makes the S3 timeout test run in microseconds instead of five seconds, and
what would let the same code run on a microcontroller with its own tick.
`UdsServer` 把 `now` 当参数而不是自己调 `time.monotonic()`。S3 超时测试因此只需微秒
而不是五秒，同一份代码也能搬到有自己 tick 的单片机上。

---

## Step by step / 分步推进

### Day 5 — run it, read it / 跑起来，读懂
- [ ] `python -m tester --channel virtual`. Match each line to a rule in the table.
- [ ] `--log session.log`, then decode two frames by hand: the FF and the FC.
  What would change if `blocksize` were 0? ______________________
- [ ] Wireshark on `vcan0`: *Analyze → Decode As → ISO-TP*, then *UDS*.
  Screenshot the VIN read. → `screenshots/wireshark-uds.png`

### Day 6 — the missing services / 缺的服务
- [ ] `0x14` ClearDiagnosticInformation: extended session only, group
  `0xFFFFFF` = all, unknown group → `0x31`. Tests first (`DtcTest` has a note).
- [ ] `0x2E` WriteDataByIdentifier: only after security access, only for
  `0xF190`–`0xF19F`, length must match. Wrong length → `0x13`.
- [ ] Brute-force protection in `_security_access`: three wrong keys → `0x36`,
  then `0x37` for 10 s. The test is written and commented out.

### Day 7 — beyond one ECU / 不止一台 ECU
- [ ] Functional addressing: listen on `0x7DF` as well. Rule: a functional
  request must **never** get a negative `0x11`/`0x12`/`0x31` response, or
  every ECU on the bus answers at once. Why? ______________________
- [ ] Point the tester at `uds-server` (project 03, target 3). Watch what
  fails and why.

- **Commit:** tests green, and they were red first.

---

## Verified / 已验证

| What | Status |
|---|---|
| `python -m unittest discover -s tests` | ✅ 49 passed (2026-09-13, udsoncan 1.26.1, can-isotp 2.0.7) |
| `python -m tester --channel virtual --log …` | ✅ run; the session output and the frames above are from that run |
| `python -m ecu` + `python -m tester` on `vcan0`, two processes | ✅ run (2026-09-13); all 14 lines identical to the virtual-bus run |
| `echo "22 F1 90" \| isotpsend -s 7E0 -d 7E8 vcan0` + `isotprecv` against `python -m ecu` | ✅ kernel ISO-TP talking to python can-isotp: `62 F1 90 57 43 41 4E …` = the VIN |
| Wireshark UDS decode | ⬜ not yet run (tshark not installed) |

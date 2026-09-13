# 04 · CAN Log Analyzer
# 04 · CAN 日志分析器

**Goal / 目标** — Turn a raw `candump` log into a per-ID inventory, a decoded
UDS conversation, a bus-load plot, and a ranked list of what went wrong.
把一份原始 `candump` 日志变成按 ID 的清单、解码后的 UDS 对话、总线负载图，
和排好序的问题清单。

**Why this project matters most / 为什么这个项目最重要** — Every job
description in this field has a line like *"analyse bus traces and support
root-cause analysis"*. Every other candidate will say they are willing to
learn it. You bring the tool, and the tool already knows what a stuck alive
counter, a stopped message and an unanswered UDS request look like.
每份 JD 都有一行"分析总线记录并支持根因分析"。别的候选人只会说"我愿意学"，
而你直接把工具带过去，而且它已经认识卡死的计数器、停掉的报文和没人回的 UDS 请求。

**Standard library only. No `pip install`.** It runs on a test rig's embedded
Linux as-is, and it does not import projects 01 or 02: a diagnostic tool must
not depend on the implementation it is diagnosing.
**只用标准库。** 能直接丢到试验台的嵌入式 Linux 上跑，也不 import 项目 01/02:
诊断工具不能依赖它所诊断的实现。

---

## Quick start / 快速开始

```bash
cd 04-can-log-analyzer

# the deliberately broken sample, with the DBC for names, cycle times and E2E
python3 -m cananalyzer samples/faulty.log --dbc samples/lab_vehicle.dbc

# a UDS session — no DBC needed, ISO-TP and UDS are decoded on their own
python3 -m cananalyzer samples/uds_session.log

# a report you can attach to a ticket
python3 -m cananalyzer samples/faulty.log --dbc samples/lab_vehicle.dbc --format html -o report.html
python3 -m cananalyzer samples/uds_session.log --format md -o report.md      # with a Mermaid sequence diagram

# machine-readable, every finding unfolded
python3 -m cananalyzer samples/faulty.log --dbc samples/lab_vehicle.dbc --format json

# CI gate
python3 -m cananalyzer samples/healthy.log --dbc samples/lab_vehicle.dbc --fail-on-error

python3 -m unittest discover -s tests -v     # 40 tests, no network, no vcan
```

Any `candump -L` log works, and so does anything python-can's `Logger`
wrote — same format.
任何 `candump -L` 的日志都行，python-can 的 `Logger` 写的也行，格式相同。

---

## What it finds / 它能发现什么

On `samples/faulty.log`, recorded from project 01 with five faults on at once:
在 `samples/faulty.log` 上 —— 项目 01 同时开五种故障录下来的:

```
findings: 18
  [ERROR  ] R005      frame 2  t=  0.001  BODY_STATUS: DLC 6 but DBC says 8 — 41 of 41 frames
  [ERROR  ] R003      frame 3  t=  0.020  ENGINE_DATA: alive counter repeated (3)
  [ERROR  ] R003      frame 9  t=  0.080  ENGINE_DATA: … 121 more like this, last at t+2.480s (frame 268)
  [ERROR  ] R004     frame 52  t=  0.480  ENGINE_DATA: CRC 0x04, computed 0xFB (DataID 17)
  [ERROR  ] R002    frame 268  t=  2.480  ENGINE_DATA: stopped 1.52 s before the end of the log (cycle 20 ms)
  [WARNING] R001     frame 47  t=  0.421  ABS_DATA: gap of 39.3 ms, expected 20 ms (dbc) — ~1 frame(s) missing
  [WARNING] R003     frame 47  t=  0.421  ABS_DATA: alive counter 4 -> 6, expected 5 (1 lost)
```

| Rule | Detects | 检测 | Needs DBC |
|---|---|---|---|
| **R001** | A cyclic message late by > 50 % of its cycle | 周期报文迟到超过半个周期 | optional — learns the cycle if absent |
| **R002** | A cyclic message that stopped before the log ended | 日志结束前就停掉的周期报文 | optional |
| **R003** | Alive counter repeated (ERROR), skipped by ≤ 3 (WARNING), or jumped (ERROR) | 计数器重复 / 小跳 / 大跳 | yes — `E2EDataId` |
| **R004** | E2E CRC mismatch | E2E CRC 不符 | yes |
| **R005** | DLC differs from the DBC | DLC 与 DBC 不符 | yes |
| **R006** | An ID the DBC does not know | DBC 里没有的 ID | yes |
| **R007** | Bus load over 70 % in any one-second window | 任一秒内总线负载超 70% | no |
| **R008** | A UDS negative response (INFO for `0x78`) | UDS 否定响应 | no |
| **R009** | A UDS request never answered, answered late, or a response without a request | 没人回、回晚了、或没请求的响应 | no |
| **R010** | ISO-TP error: sequence, truncated, CF without FF | ISO-TP 错误 | no |

**R001 is the one worth pointing at:** with no DBC it *learns* the cycle time
from the log itself, requiring 70 % of the gaps to sit within 20 % of the median, so that one 800 ms
hole in a 100 ms message is what gets reported, not what stops the learning.
**R001 值得单独指出:** 没有 DBC 时它从日志本身学周期，要求七成的间隔落在中位数 ±20% 内，
所以 100 ms 报文里的一个 800 ms 洞是被报告的对象，而不是妨碍学习的干扰。

**And the one that is deliberately missing:** `samples/jitter.log` was
recorded with `--fault jitter=10` and no rule catches it. R011 is yours.
**故意缺的那条:** `samples/jitter.log` 是开着 `--fault jitter=10` 录的，没有规则能抓到。R011 归你。

---

## Architecture / 架构

```
candump log
   │
   ▼
parsers/candump.py   sniff() + parse()  ──►  list[Frame]        (11/29-bit, FD, remote, direction flag)
   │
   ├──► dbc_lite.py       BO_/SG_/BA_ subset  ──►  {id: MessageDef}   (Intel decode done; Motorola is TODO(you))
   │
   ├──► isotp.py          SF/FF/CF/FC reassembly per ID  ──►  IsoTpMessage, FlowControl
   │        │
   │        ▼
   │    uds.py            SID/NRC tables, request↔response pairing, 0x78 handling, latency
   │
   ▼
rules.py             Context → prepare() → R001..R010 → coalesce() → list[Finding]
   │
   ▼
render.py            text | json | md (+ mermaid) | html (+ SVG bus-load plot)
```

**Three design decisions to defend / 要辩护的三个设计决策:**

1. **The CRC is re-implemented, not imported from project 01.** Twelve lines
   of duplication buy independence: if project 01's CRC were wrong, a tool
   that imported it would agree with the bug.
   CRC 重新实现而不是 import 项目 01。十二行重复换来独立性: 如果项目 01 的 CRC 错了，
   import 它的工具会和 bug 保持一致。
2. **Rules are functions over a prepared `Context`, not classes with state.**
   Adding R011 is one function and one line in `RULES`. Every rule sees the
   same reassembled ISO-TP messages and paired transactions; none re-parses.
   规则是作用在预处理好的 `Context` 上的函数。加 R011 就是一个函数加一行注册。
3. **`coalesce()` folds repeats in text/md/html but not in json.** A stuck
   counter is one fact, not 124; a human should see it once. A machine
   consuming the JSON may want every frame index.
   折叠只作用于给人看的格式。卡死的计数器是一个事实，不是 124 个。

---

## Step by step / 分步推进

### Day 11 — rules / 规则
- [ ] Read `rules.py` top to bottom. Run every sample with `--format text`.
- [ ] R011 jitter: `pstdev(gaps) > 20 %` of the expected cycle → WARNING.
  It must fire on `samples/jitter.log` and stay quiet on `healthy.log`.
- [ ] R012 brute force: ≥ 3 × NRC `0x35` on one request ID within 60 s → ERROR.
  Write in a comment why the *analyzer* needs this rule even though the ECU
  should refuse after three: ______________________
- [ ] Run it on your ICSim capture from project 03 with no DBC. What does it
  learn on its own? What is it blind to?

### Day 12 — Motorola / Motorola 字节序
- [ ] `dbc_lite.decode_signal`, the `else:` branch. Uncomment the two tests.
- [ ] `--format html` on `faulty.log`, open it. The "Last decoded" column now
  shows `OutsideTemp`. Add one more column you wish it had.

### Day 13 — a fault no rule catches / 没有规则能抓的故障
- [ ] Add one to project 01. Ideas: content frozen while counter and CRC keep
  going; one ID sent by two nodes; a gateway halving the cycle.
- [ ] Record it, add the rule, add the sample, add the test.

- **Commit:** tests green, and they were red first.

---

## Verified / 已验证

| What | Status |
|---|---|
| `python3 -m unittest discover -s tests` | ✅ 40 passed (2026-09-13, Python 3.13, system interpreter, no venv) |
| All four samples, all five formats | ✅ run; `samples/report-*.{md,html,txt}` are the outputs |
| `samples/*.log` provenance | ✅ recorded from projects 01 and 02 on the in-process virtual bus (channel names `lab` / `uds`), not from `vcan0` |
| A log from real `candump -L vcan0` | ✅ `../03-bus-analysis/captures/vcan-real.log`, project 01 with `--fault drop-abs=0.05 --fault bad-crc=30`: R004 × 8, R001/R003 × 16 including the wrap-around `14 -> 1, expected 0` |

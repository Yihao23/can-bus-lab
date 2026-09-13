# Bus analysis report 01 / 总线分析报告 01

Copy to `REPORT-01.md`. Every claim points at a capture file and a line number
or timestamp. A claim without a pointer is an opinion.
复制为 `REPORT-01.md`。每个断言都指向一个抓包文件和行号/时间戳。没有指向的断言只是观点。

## 1. Setup / 环境

| | |
|---|---|
| Date / 日期 | |
| Kernel, can-utils version | `uname -r`, `candump --version` |
| Targets / 靶子 | ICSim commit ___, seed ___; uds-server commit ___ |
| Captures / 抓包 | `captures/icsim-idle.log`, `captures/icsim-drive.log`, … |

## 2. Inventory / 清单 (from `idstat.py`)

Paste the `.idstat` output. Then, per ID, one line: cyclic/event, period,
which bytes move, your guess.
贴 `.idstat` 输出。然后每个 ID 一行: 周期/事件、周期值、哪些字节动、你的猜测。

| ID | kind | period | changing bytes | hypothesis |
|---|---|---|---|---|
| | | | | |

## 3. Signals found / 找到的信号

For each signal: the experiment (what you did, when), the evidence (frames
before / after), the DBC line, and the proof (`cantools decode` output that
matches the experiment).
每个信号: 实验(做了什么、什么时候)、证据(前后帧)、DBC 行、证明。

### 3.1 Vehicle speed / 车速

- Experiment:
- Evidence: `captures/icsim-drive.log` lines ___–___
- DBC: `SG_ Speed : 8|16@0+ (…) [0|…] "mph"` ← fill in the real one
- Proof:
- Byte order and why you know: ______________________

### 3.2 Doors / 车门
### 3.3 Indicators / 转向灯

## 4. Diagnostics / 诊断 (uds-server)

| Question | Answer | Evidence |
|---|---|---|
| Which IDs respond to `0x3E`? | | `caringcaribou uds discovery` output |
| Which services? | | |
| Which DIDs in `0xF180–0xF1FF`? | | |
| Does it implement `0x27`? What happens with a wrong key? | | |
| Does it send `0x78`? | | |

## 5. Our tester against a foreign ECU / 我们的诊断仪 vs 别人的 ECU

Run project 02's `python -m tester` against uds-server. For each line that
differs from the project 02 output, say why. (There will be several: DID
table, seed/key, session rules.)
每一行不同都要解释原因。

## 6. What I could not determine and why / 没能确定的和原因

Be specific. "Byte 3 of 0x244 changes but I could not correlate it with any
control" is a finding.
要具体。"0x244 的第 3 字节会变但我关联不到任何操作"本身就是发现。

## 7. What this would look like on a real car / 在真车上会是什么样

Two paragraphs: what is the same (the four moves, the tools), what is
different (gateways, multiple buses, E2E, no `-r` seed, 500 kbit/s of noise).
两段: 哪些一样，哪些不一样。

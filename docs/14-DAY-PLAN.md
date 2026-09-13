# 14-Day Plan / 两周计划

One rule: **every day ends with something committed.** A day that produces
only reading produces nothing you can show.
一条规则: **每天结束时都要有东西提交。** 只有阅读的一天，等于没有产出。

---

## Week 1 — Build / 第一周 · 造

### Day 1 · Concepts + the wire / 概念 + 线上

- [ ] Read [`GLOSSARY.md`](GLOSSARY.md) top to bottom. Close it. Draw the CAN
  frame field by field, then the error-state machine (active → passive →
  bus-off) with the counter thresholds. Check yourself.
- [ ] `sudo apt install can-utils`, `sudo setup/vcan-up.sh`, `setup/bootstrap.sh`.
- [ ] `cangen vcan0 -v` in one terminal, `candump vcan0` in another. Then
  `cansend vcan0 123#DEADBEEF`. Then `candump -L vcan0 > first.log` for 10 s.
- [ ] Answer in one sentence each: Why does the lowest ID win? Why does a lone
  node on a bus retry forever? Why is bus-off silent?

- **Commit:** `docs/notes-day1.md` with the drawings (photo is fine).

### Day 2 · Project 01 end to end / 项目 01 跑通

- [ ] `python -m vehicle --dashboard` on vcan0, `candump -td -c vcan0` alongside,
  the cluster page open in a browser. Match one frame on the page to the DBC.
- [ ] Decode one `100#` and one `300#` frame by hand. `cantools decode` to check.
- [ ] Wireshark on vcan0: filter `can.id == 0x1A0`, add `can.data` column.

- **Commit:** your hand-decoding in `01-virtual-vehicle/notes.md`.

### Day 3 · E2E receiver / E2E 接收端

- [ ] `tests/test_e2e.py`: uncomment the receiver tests. Red.
- [ ] Implement `E2EReceiver.check()`. Green. Decide `MaxDeltaCounter`; write why.
- [ ] `--fault stuck-counter` and `--fault drop-abs=0.2` now report.

- **Commit:** tests green, and they were red first.

### Day 4 · Timeouts and 29-bit / 超时和 29 位

- [ ] `ClusterEcu.check_timeouts()` + a test with `engine_stop_after`.
- [ ] Add a J1939 CCVS (PGN 0xFEF1) message: 29-bit ID, 100 ms, DBC + sender.
- [ ] Answer: speedometer on ABS timeout — last value or zero? Write it down.

- **Commit:** the DBC with four messages.

### Day 5 · UDS session / UDS 会话

- [ ] `python -m tester --channel virtual`. Map every line to the NRC table.
- [ ] Two terminals on vcan0, `candump` in a third. Decode the FF and FC by hand.
- [ ] Wireshark: *Decode As → ISO-TP → UDS*. 📸 `screenshots/wireshark-uds.png`.
- [ ] `isotpsend` / `isotprecv` from can-utils against `python -m ecu`.

- **Commit:** the screenshot and the hand-decoding.

### Day 6 · Missing services / 缺的服务

- [ ] `0x14` ClearDiagnosticInformation. `0x2E` WriteDataByIdentifier.
- [ ] Brute-force lockout: `0x36` after three bad keys, `0x37` during the delay.
- [ ] Uncomment the waiting test. Red → green.

- **Commit:** three services, tests first.

### Day 7 · Functional addressing / 功能寻址

- [ ] Listen on `0x7DF` too. Rule: never answer `0x11`/`0x12`/`0x31` to a
  functional request. Write why in the README.
- [ ] Write project 02's README section on what you added.

- **Commit:** the functional stack.

---

## Week 2 — Read, break, explain / 第二周 · 读、搞坏、讲清楚

### Day 8 · Tools on a known bus / 熟悉的总线上学工具

- [ ] Project 01 for 60 s, `03-bus-analysis/setup/capture.sh known 30`.
- [ ] Read the `.idstat`. `cansend` a forged `100#` frame; watch the cluster.
- [ ] `canplayer -I known.log vcan0` — replay. Then `cangen -g 1 -I 100 vcan0`
  and watch project 04 report R001/R003/R004 on the mess.

- **Commit:** `captures/known.idstat`.

### Day 9 · ICSim blind / ICSim 盲做

- [ ] Build ICSim. `-r 1234`. Capture while doing one thing at a time.
- [ ] Find speed, doors, indicators. Write the DBC lines. Prove them with
  `cantools decode`. `cansend` the speedometer to 88.
- [ ] REPORT §2–3.

- **Commit:** `report/REPORT-01.md` §1–3 and one screenshot.

### Day 10 · uds-server blind / uds-server 盲做

- [ ] Build uds-server. `caringcaribou uds discovery / services / dump_dids`.
- [ ] Project 02's tester against it: explain every difference.
- [ ] REPORT §4–7.

- **Commit:** REPORT complete.

### Day 11 · Analyzer rules / 分析器规则

- [ ] Read `rules.py` top to bottom; run every sample with `--format text`.
- [ ] R011 jitter (catches `samples/jitter.log`). R012 brute force.
- [ ] Run the analyzer on your ICSim capture *without* a DBC. What does it
  learn on its own? What can it not know?

- **Commit:** two rules, tests first.

### Day 12 · Motorola decode / Motorola 解码

- [ ] `dbc_lite.decode_signal` Motorola branch. Uncomment the test. Red → green.
- [ ] `--format html` on `faulty.log`; open it. Add one column you wish it had.

- **Commit:** the decoder and a generated `samples/report-faulty.html`.

### Day 13 · Break it in new ways / 用新方法搞坏

- [ ] Add a fault to project 01 that no rule catches. Then add the rule.
  (Ideas: a message whose *content* is stale while counter and CRC are fine;
  an ID sent by two nodes; a gateway that halves the cycle.)
- [ ] `cangen -g 0 vcan0` for 5 s while project 01 runs: bus load through the
  roof. Does R007 fire? Does the cluster survive?

- **Commit:** fault + rule + sample.

### Day 14 · Say it out loud / 说出声

- [ ] `INTERVIEW-QA.md`: answer every question out loud, with the artefact on
  screen. Time yourself: two minutes per answer, max.
- [ ] Root README: fill the "What the four projects found" section with what
  *you* found, not what the template says.
- [ ] Optional: project 05, real hardware. Two Nucleo boards + two transceivers
  + a 1 m twisted pair. Remove one terminator and *watch* the error counters.

- **Commit:** the README. Push. Send the link.

# Glossary / 术语表

Read it once top to bottom. Then close it and draw the CAN frame and the
UDS-over-ISO-TP-over-CAN stack from memory.
从头到尾读一遍，合上，默画 CAN 帧和 UDS/ISO-TP/CAN 协议栈。

---

## The bus / 总线

| Term | Meaning | 含义 |
|---|---|---|
| **CAN** | Controller Area Network, ISO 11898. Multi-master serial bus, two wires, no addresses — every frame is broadcast, and the identifier says *what* it carries, not *who* sent it. | 多主串行总线，两根线，没有地址 —— 每帧都是广播，ID 表示"内容是什么"，不是"谁发的"。 |
| **CAN_H / CAN_L** | The differential pair. Dominant = CAN_H ≈ 3.5 V, CAN_L ≈ 1.5 V (logic 0). Recessive = both ≈ 2.5 V (logic 1). Dominant always wins over recessive on the wire. | 差分对。显性 = 逻辑 0，隐性 = 逻辑 1。线上显性永远压过隐性。 |
| **Termination** | 120 Ω at each physical end of the bus, so the pair looks like 60 Ω. Missing one end → reflections → errors at high bit rates. Measuring 60 Ω between CAN_H and CAN_L with power off is the first field check. | 两端各 120 Ω，总线看起来是 60 Ω。断电测 CAN_H–CAN_L 得 60 Ω 是现场第一步检查。 |
| **Transceiver** | The chip between controller (digital TX/RX) and the wire (differential). TJA1050, MCP2551, TJA1042. | 控制器和线之间的芯片。 |
| **Controller** | The peripheral that does framing, arbitration, CRC, ACK, error counters. Inside the MCU (bxCAN, FDCAN, MCAN) or external (MCP2515). | 做成帧、仲裁、CRC、ACK、错误计数的外设。 |
| **Bit rate** | Classic CAN up to 1 Mbit/s; 500 kbit/s is the automotive default for powertrain, 125 kbit/s for body. CAN FD up to 5–8 Mbit/s in the data phase. | 经典 CAN 最高 1 Mbit/s，动力总线常用 500k，车身 125k。 |
| **Bit timing** | One bit = Sync_Seg + Prop_Seg + Phase_Seg1 + Phase_Seg2, in time quanta. Sample point ≈ 75–87.5 %. All nodes must agree. | 一个位由几个时间段组成，采样点 75–87.5%，所有节点必须一致。 |
| **Bus load** | Fraction of time the bus is busy. Compute, do not guess: Σ(frame bits × rate) / bit rate. Design ceiling ≈ 70 %. | 总线忙的时间占比。算出来，不要猜。设计上限约 70%。 |

## The frame / 帧

| Term | Meaning | 含义 |
|---|---|---|
| **SOF** | Start of frame, one dominant bit. | 帧起始。 |
| **Identifier** | 11 bits (standard, CAN 2.0A) or 29 bits (extended, CAN 2.0B). Lower value = higher priority. | 11 位或 29 位。数值越小优先级越高。 |
| **RTR** | Remote transmission request — asks another node to send. Practically unused in cars; not in CAN FD. | 远程帧，车上基本不用。 |
| **IDE** | Identifier extension bit: 0 = 11-bit, 1 = 29-bit. | 标准/扩展标志。 |
| **DLC** | Data length code, 4 bits. 0–8 bytes in classic CAN; in CAN FD codes 9–15 mean 12/16/20/24/32/48/64 bytes. | 数据长度码。 |
| **CRC** | 15 bits in classic CAN, 17 or 21 in CAN FD. Protects the frame on the wire only. | 只保护"线上"这一段。 |
| **ACK slot** | Every receiving node that got a valid CRC drives one dominant bit. A sender with no other node on the bus sees no ACK → error → retries forever (the classic "single node" mistake). | 每个收到有效 CRC 的节点打一个显性位。总线上只有一个节点时永远收不到 ACK。 |
| **EOF / IFS** | 7 recessive bits end of frame, 3 bits inter-frame space. | 帧结束 7 位隐性，帧间隔 3 位。 |
| **Bit stuffing** | After 5 identical bits the sender inserts one opposite bit; the receiver removes it. Keeps edges for clock sync. Applies SOF → CRC. Worst case adds ~20 % to the frame. | 连续 5 个相同位后插一个相反位，为了时钟同步。最坏情况帧长 +20%。 |
| **Arbitration** | Nodes start together; each sends its ID bit by bit and reads the bus back. A node that sent recessive but reads dominant has lost; it stops and retries after this frame. Non-destructive: the winner never notices. | 各节点逐位发 ID 并回读。发隐性却读到显性的节点退出。非破坏性: 赢家毫无感觉。 |

## Errors / 错误

| Term | Meaning | 含义 |
|---|---|---|
| **Error frame** | 6 dominant bits (violates stuffing on purpose) so every node discards the frame. Followed by the sender retrying. | 6 个显性位故意破坏填充规则，让所有节点丢弃这帧。 |
| **Five error types** | Bit error, stuff error, CRC error, form error, ACK error. | 位错误、填充错误、CRC 错误、格式错误、应答错误。 |
| **TEC / REC** | Transmit / receive error counters. +8 on a TX error, +1 on RX, −1 per good frame. | 发送/接收错误计数器。 |
| **Error active** | Normal. TEC and REC < 128. Sends active (dominant) error flags. | 正常状态。 |
| **Error passive** | TEC or REC ≥ 128. Sends passive (recessive) error flags and waits 8 extra bits before transmitting — a sick node throttled so it cannot take the bus down. | 计数 ≥ 128。病节点被限速，免得拖垮总线。 |
| **Bus-off** | TEC > 255. The node disconnects itself. Recovery after 128 × 11 recessive bits, usually triggered by software. **A bus-off node is silent — it produces no error frames, just absence.** | 计数 > 255，节点自我断开。**bus-off 的节点是沉默的，没有错误帧，只有缺席。** |

## Above the frame / 帧之上

| Term | Meaning | 含义 |
|---|---|---|
| **DBC** | Vector's database format: which ID is which message, which bits are which signal, factor/offset/unit, cycle time, sender/receivers. The contract between ECUs. | Vector 的数据库格式。ECU 之间的契约。 |
| **Signal** | Start bit + length + byte order + sign + factor + offset. Physical = raw × factor + offset. | 物理值 = 原始值 × 因子 + 偏移。 |
| **Intel / Motorola** | Little-endian / big-endian signal layout. DBC `@1` = Intel, `@0` = Motorola. Motorola's start bit is the MSB, numbered in the "sawtooth" scheme, and is the single most common source of decoding bugs. | 小端/大端。Motorola 起始位是 MSB，锯齿编号，是解码 bug 的头号来源。 |
| **Cycle time** | Period of a cyclic message. 10 ms powertrain, 20–100 ms chassis, 100–1000 ms body. | 周期报文的周期。 |
| **E2E** | AUTOSAR End-to-End protection: alive counter + CRC + DataID over the payload. Detects what CAN's CRC cannot: repetition, loss, reorder, masquerade, stale data. | AUTOSAR 端到端保护。发现 CAN CRC 发现不了的东西: 重复、丢失、乱序、冒充、过期。 |
| **Gateway** | ECU on two or more buses, forwarding selected messages. Adds latency; the place where DLC and cycle mismatches are born. `can-gw` on Linux. | 跨总线转发的 ECU。延迟和不匹配的诞生地。 |
| **SocketCAN** | Linux's CAN stack: CAN interfaces are network interfaces (`can0`, `vcan0`), frames are sockets. `candump`, `cansend`, `cangen`, `canplayer`, `isotpsend` from can-utils. | Linux 的 CAN 栈: CAN 接口就是网络接口。 |
| **vcan** | Virtual CAN interface. No arbitration, no errors, no physical layer — a kernel queue that looks like a bus. | 虚拟接口。没有仲裁、没有错误、没有物理层。 |

## Diagnostics / 诊断

| Term | Meaning | 含义 |
|---|---|---|
| **ISO-TP** | ISO 15765-2, transport protocol. Segments up to 4095 bytes into CAN frames: SF, FF, CF, FC. Flow control carries block size and STmin. | 传输层。单帧/首帧/连续帧/流控。 |
| **UDS** | ISO 14229, Unified Diagnostic Services. Request = SID + parameters; positive response = SID + 0x40; negative = `7F SID NRC`. | 统一诊断服务。正响应 SID+0x40，负响应 7F SID NRC。 |
| **SID** | Service identifier. 0x10 session, 0x22 read DID, 0x27 security, 0x19 DTCs, 0x3E tester present, 0x11 reset, 0x2E write DID, 0x31 routine, 0x34/36/37 download. | 服务号。 |
| **DID** | Data identifier, 16 bit. 0xF190 VIN, 0xF18C serial, 0xF195 SW version are standardised. | 数据标识符。 |
| **DTC** | Diagnostic trouble code, 3 bytes + status byte. P0301 = misfire cyl 1; U0073 = bus-off. Status bits: testFailed, pending, confirmed. | 故障码。 |
| **NRC** | Negative response code. 0x11 not supported, 0x12 sub-function, 0x13 length, 0x22 conditions, 0x31 out of range, 0x33 security, 0x35 invalid key, 0x78 pending, 0x7F not in this session. | 否定响应码。 |
| **Session** | Default (0x01), programming (0x02), extended (0x03). Falls back to default after S3 (5 s) without TesterPresent. | 会话。S3 = 5 s 没有 TesterPresent 就回默认。 |
| **P2 / P2\*** | Tester timeouts: 50 ms for a response; 5 s after an NRC 0x78. | 诊断仪超时: 50 ms；收到 0x78 后改 5 s。 |
| **Seed / key** | SecurityAccess: ECU sends a random seed, tester answers with f(seed). f is secret per OEM. | 安全访问: ECU 发种子，诊断仪回 f(种子)。 |
| **OBD-II** | ISO 15031 / SAE J1979, the legal-minimum emissions diagnostics on 0x7DF/0x7E8, "mode 01 PID 0C" = RPM. Same ISO-TP, different services. | 法规要求的排放诊断，同样走 ISO-TP，服务不同。 |
| **ODX / PDX** | ASAM diagnostic description of an ECU (DIDs, DTCs, sessions) that a workshop tester loads. Without it, a tester cannot decode a multi-DID reply. | ECU 的诊断描述文件，没有它诊断仪拆不开多 DID 响应。 |

## Neighbours / 邻居

| Term | Meaning | 含义 |
|---|---|---|
| **CAN FD** | ISO 11898-1:2015. Up to 64 bytes, higher bit rate in the data phase (BRS), longer CRC, no RTR. Same arbitration. | 64 字节，数据段提速，同样的仲裁。 |
| **CAN XL** | 2048 bytes, up to 20 Mbit/s, 2023+. | 更新的扩展。 |
| **J1939** | SAE, heavy vehicles. 29-bit ID carries priority + PGN + source address; PGNs standardise content (0xFEF1 CCVS = cruise/vehicle speed). Multi-packet via TP.CM/TP.DT. | 商用车。29 位 ID 里含 PGN 和源地址。 |
| **LIN** | Single wire, 20 kbit/s, master/slave, for mirrors, seats, switches. Cheap. | 单线，主从，便宜。 |
| **FlexRay** | 10 Mbit/s, time-triggered, dual channel, for X-by-wire. Being replaced by Ethernet. | 时间触发，正在被以太网取代。 |
| **Automotive Ethernet** | 100BASE-T1 / 1000BASE-T1, one pair. Backbone; CAN survives at the edges. | 骨干网，CAN 留在边缘。 |
| **XCP** | ASAM calibration/measurement protocol over CAN or Ethernet — read/write ECU variables at runtime. | 标定/测量协议。 |
| **AUTOSAR CAN stack** | Can (driver) → CanIf → PduR → Com (signals) / CanTp (ISO-TP) → Dcm (UDS). | 驱动 → 接口 → 路由 → 信号/传输 → 诊断。 |

# CAN log report

357 frames, 3 IDs, 4.00 s, 0 UDS transactions.

## Findings

| Sev | Rule | t (s) | Subject | Message |
|---|---|---|---|---|
| ERROR | R005 | 0.001 | BODY_STATUS | DLC 6 but DBC says 8 — 41 of 41 frames |
| ERROR | R003 | 0.020 | ENGINE_DATA | alive counter repeated (3) |
| ERROR | R003 | 0.040 | ENGINE_DATA | alive counter repeated (3) |
| ERROR | R003 | 0.060 | ENGINE_DATA | alive counter repeated (3) |
| ERROR | R003 | 0.080 | ENGINE_DATA | … 121 more like this, last at t+2.480s (frame 268) |
| ERROR | R004 | 0.480 | ENGINE_DATA | CRC 0x04, computed 0xFB (DataID 17) |
| ERROR | R004 | 0.980 | ENGINE_DATA | CRC 0x2B, computed 0xD4 (DataID 17) |
| ERROR | R004 | 1.481 | ENGINE_DATA | CRC 0x8F, computed 0x70 (DataID 17) |
| ERROR | R004 | 1.980 | ENGINE_DATA | … 2 more like this, last at t+2.480s (frame 268) |
| ERROR | R002 | 2.480 | ENGINE_DATA | stopped 1.52 s before the end of the log (cycle 20 ms) |
| WARNING | R001 | 0.421 | ABS_DATA | gap of 39.3 ms, expected 20 ms (dbc) — ~1 frame(s) missing |
| WARNING | R003 | 0.421 | ABS_DATA | alive counter 4 -> 6, expected 5 (1 lost) |
| WARNING | R001 | 0.801 | ABS_DATA | gap of 40.0 ms, expected 20 ms (dbc) — ~1 frame(s) missing |
| WARNING | R003 | 0.801 | ABS_DATA | alive counter 8 -> 10, expected 9 (1 lost) |
| WARNING | R001 | 1.461 | ABS_DATA | gap of 40.1 ms, expected 20 ms (dbc) — ~1 frame(s) missing |
| WARNING | R003 | 1.461 | ABS_DATA | alive counter 11 -> 13, expected 12 (1 lost) |
| WARNING | R001 | 1.601 | ABS_DATA | … 7 more like this, last at t+3.520s (frame 327) |
| WARNING | R003 | 1.601 | ABS_DATA | … 7 more like this, last at t+3.520s (frame 327) |

## Messages

| ID | Name | Count | Period (ms) | Expected | DLC | Last decoded |
|---|---|---|---|---|---|---|
| 0x100 | ENGINE_DATA | 125 | 20.0 | 20.0 dbc | 8 | EngineSpeed=1968, ThrottlePos=44.8, CoolantTemp=25, EngineRunning=1, ENGINE_DATA_Counter=3, ENGINE_DATA_CRC=41 |
| 0x1A0 | ABS_DATA | 191 | 20.0 | 20.0 dbc | 8 | VehicleSpeed=30.02, WheelSpeedFL=30.3, WheelSpeedFR=29.7, BrakeActive=0, ABS_DATA_Counter=5, ABS_DATA_CRC=83 |
| 0x300 | BODY_STATUS | 41 | 100.0 | 100.0 dbc | 6 |  |

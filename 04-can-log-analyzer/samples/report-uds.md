# CAN log report

46 frames, 2 IDs, 0.31 s, 15 UDS transactions.

## Findings

| Sev | Rule | t (s) | Subject | Message |
|---|---|---|---|---|
| WARNING | R008 | 0.002 | UDS | ReadDataByIdentifier -> NRC 0x33 securityAccessDenied |
| WARNING | R008 | 0.003 | UDS | SecurityAccess -> NRC 0x7F serviceNotSupportedInActiveSession |
| WARNING | R008 | 0.006 | UDS | ReadDataByIdentifier -> NRC 0x31 requestOutOfRange |
| WARNING | R008 | 0.310 | UDS | … 1 more like this, last at t+0.307s (frame 45) |
| INFO | R008 | 0.007 | UDS | ReadDataByIdentifier -> NRC 0x78 requestCorrectlyReceivedResponsePending |

## Messages

| ID | Name | Count | Period (ms) | Expected | DLC | Last decoded |
|---|---|---|---|---|---|---|
| 0x7E0 |  | 19 | 0.5 | -  | 8 |  |
| 0x7E8 |  | 27 | 0.4 | -  | 8 |  |

## UDS

```mermaid
sequenceDiagram
    participant T as Tester
    participant E as ECU
    T->>E: ReadDataByIdentifier  f1 90
    E->>T: ReadDataByIdentifier +  f1 90 57 43 41 4e 4c 41…
    T->>E: ReadDataByIdentifier  01 00
    E->>T: ReadDataByIdentifier +  01 00 0d 48
    T->>E: ReadDataByIdentifier  f1 a0
    E-->>T: NRC 0x33 securityAccessDenied
    T->>E: SecurityAccess  01
    E-->>T: NRC 0x7F serviceNotSupportedInActiveSession
    T->>E: DiagnosticSessionControl  03
    E->>T: DiagnosticSessionControl +  03 00 32 01 f4
    T->>E: SecurityAccess  01
    E->>T: SecurityAccess +  01 12 34 56 78
    T->>E: SecurityAccess  02 b7 92 f5 e0
    E->>T: SecurityAccess +  02
    T->>E: ReadDataByIdentifier  f1 a0
    E->>T: ReadDataByIdentifier +  f1 a0 43 41 4c 2d 32 30…
    T->>E: ReadDataByIdentifier  f1 87 f1 8c f1 95
    E->>T: ReadDataByIdentifier +  f1 87 43 41 4e 4c 41 42…
    T->>E: ReadDataByIdentifier  de ad
    E-->>T: NRC 0x31 requestOutOfRange
    T->>E: ReadDataByIdentifier  02 00
    E-->>T: NRC 0x78 requestCorrectlyReceivedResponsePending
    E->>T: ReadDataByIdentifier +  02 00 de ad
    T->>E: ReadDTCInformation  01 09
    E->>T: ReadDTCInformation +  01 4d 01 00 02
    T->>E: ReadDTCInformation  02 ff
    E->>T: ReadDTCInformation +  02 4d 01 1f 00 09 03 01…
    T->>E: TesterPresent  00
    E->>T: TesterPresent +  00
    T->>E: ECUReset  01
    E-->>T: NRC 0x22 conditionsNotCorrect
```

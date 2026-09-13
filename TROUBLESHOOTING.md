# Troubleshooting / 排障

| Symptom | Cause | Fix |
|---|---|---|
| `Device "vcan0" does not exist` | Interface not created since last boot | `sudo setup/vcan-up.sh` |
| `RTNETLINK answers: Operation not permitted` | `ip link` needs root | `sudo …` |
| `modprobe: FATAL: Module vcan not found` | Kernel without CAN (some cloud / WSL1 kernels) | WSL2 needs a custom kernel with `CONFIG_CAN_VCAN`; or use `--channel virtual` everywhere, which needs no kernel |
| `candump: command not found` | can-utils not installed | `sudo apt install can-utils` |
| `OSError: [Errno 19] No such device` from python-can | `--channel vcan0` but no vcan0 | as above, or `--channel virtual` |
| `python -m vehicle` runs but `candump vcan0` shows nothing | Two different channels: vehicle on `virtual`, candump on `vcan0` | Drop `--channel virtual` |
| `candump` shows frames but the cluster reports `unknown ids` | Something else is on vcan0 (ICSim, cangen) | `ip -s link show vcan0`, kill the other sender, or filter: `candump vcan0,100:7FF` |
| Project 02 tester: `TimeoutException` on every request | No ECU running, or ECU on another channel | `python -m ecu -v` first, same `--channel` |
| Tester: `NRC 0x7F` on SecurityAccess | You are in the default session | That is correct behaviour — `change_session(3)` first |
| Tester: `NRC 0x35 invalidKey` against uds-server | Their seed/key is not ours | Expected. Project 03 §5 is about exactly this |
| udsoncan: `ConfigError: … no definition for data identifier` | The tester needs a codec per DID | Add it to `client_config()` in `tester/client.py` |
| Analyzer says `not a candump log` | Log written by `candump` without `-L`, or by `candump -l` (creates `candump-*.log`, fine) | Use `candump -L vcan0 > x.log`, or `python-can`'s `Logger` |
| Analyzer: every ID `R006 not in DBC` | Wrong DBC, or IDs are 29-bit and the DBC has them without the 0x80000000 flag | Check `BO_` IDs; `dbc_lite` strips the flag |
| Analyzer reports R001 gaps on a log from the in-process virtual bus | Python thread scheduling jitter, especially on a loaded laptop | Real; that is why `samples/jitter.log` exists. R011 is the TODO |
| `cantools decode` shows `OutsideTemp` but `cananalyzer` does not | Motorola decode is `TODO(you)` in `dbc_lite.py` | Day 12 |
| ICSim: `error while loading shared libraries: libSDL2` | SDL2 not installed | `sudo apt install libsdl2-dev libsdl2-image-dev` |
| Wireshark shows raw `CAN` frames but no `ISO-TP` / `UDS` tree | Dissector not enabled for these IDs | *Analyze → Decode As → CAN next level protocol → ISO 15765*, then *UDS* |
| Tests hang after a failure in project 02 | An ISO-TP thread outlived the test | Ctrl-C; the fixture's `finally` block stops it on the next run — report it if it recurs |

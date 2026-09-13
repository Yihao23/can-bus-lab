# Bringing up the targets / 把靶子跑起来

Everything below needs a real `vcan0`. Once, after every reboot:
下面所有内容都需要真正的 `vcan0`。每次重启后执行一次:

```bash
sudo ../../setup/vcan-up.sh        # modprobe vcan can-isotp; ip link add vcan0
```

## Target 1 — our own vehicle (project 01) / 靶子 1: 自己的整车

```bash
cd ../01-virtual-vehicle && source ../.venv/bin/activate
python -m vehicle --duration 60
```

You know this bus. Use it to learn the *tools*, not the traffic.
这条总线你熟。用它学工具，不是学流量。

## Target 2 — ICSim, a bus you do not know / 靶子 2: 一条你不认识的总线

[ICSim](https://github.com/zombieCraig/ICSim) is an instrument cluster plus a
controller. The controller sends speed, doors, indicators on IDs it does not
tell you. **The point of this project is finding them.**
ICSim 是一块仪表加一个控制器。控制器往你不知道的 ID 上发车速、车门、转向灯。
**这个项目的意义就是把它们找出来。**

```bash
sudo apt install libsdl2-dev libsdl2-image-dev can-utils
git clone https://github.com/zombieCraig/ICSim ~/codespace/ICSim && cd ~/codespace/ICSim
make
./icsim vcan0 &          # the dashboard
./controls vcan0         # the "car": arrow keys = accelerate/turn, etc.
```

ICSim randomises its IDs with `-r <seed>`; use `-r 1234` the first time so you
can compare notes with the report template, then a random seed to prove you
can do it blind.
ICSim 可以用 `-r <seed>` 随机化 ID；第一次用 `-r 1234`，好和报告模板对答案，
然后换随机种子证明你能盲做。

## Target 3 — uds-server, an ECU you do not know / 靶子 3: 一台你不认识的 ECU

```bash
git clone https://github.com/zombieCraig/uds-server ~/codespace/uds-server && cd ~/codespace/uds-server
make
./uds-server -v vcan0
```

Now point project 02's tester at it — and watch it fail, because its DIDs and
its seed/key are not ours. Then use `caringcaribou` to *discover* what it does
support:
现在把项目 02 的诊断仪指向它 —— 看着它失败，因为 DID 和种子密钥都不是我们的。
然后用 `caringcaribou` 去*发现*它到底支持什么:

```bash
pip install caringcaribou
caringcaribou uds discovery -min 0x700 -max 0x7FF          # which IDs answer at all
caringcaribou uds services 0x7E0 0x7E8                     # which SIDs
caringcaribou uds dump_dids 0x7E0 0x7E8 --min_did 0xF180 --max_did 0xF1FF
```

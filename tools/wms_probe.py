#!/usr/bin/env python3
"""Standalone test tool for the (old) Warema WMS WebControl.

Only uses the Python standard library, so it runs on any machine in the LAN:

    python3 tools/wms_probe.py 192.168.1.50 list
    python3 tools/wms_probe.py 192.168.1.50 state 0 1
    python3 tools/wms_probe.py 192.168.1.50 move 0 1 --position 50
    python3 tools/wms_probe.py 192.168.1.50 move 0 1 --position 100 --angle 170
    python3 tools/wms_probe.py 192.168.1.50 watch 0 1

Room and channel are 0-based indexes, in the order shown in the WebControl UI.
Position: 0 = fully up/retracted, 100 = fully down/extended.
Angle is the raw slat value the WebControl reports as <winkel> (255 = none).
"""

import argparse
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class WebControl:
    def __init__(self, host: str, delay: float = 0.3) -> None:
        if not host.startswith("http"):
            host = f"http://{host}"
        self.url = host.rstrip("/") + "/protocol.xml"
        self.delay = delay
        self.counter = 0
        self.ts = int(time.time())

    def send(self, cmd: str) -> ET.Element:
        payload = f"90{self.counter:02x}{cmd}"
        self.counter = (self.counter + 1) % 256
        self.ts += 1
        query = urllib.parse.urlencode({"protocol": payload, "_": self.ts})
        with urllib.request.urlopen(f"{self.url}?{query}", timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        time.sleep(self.delay)
        return ET.fromstring(text)

    def ready(self, room: int, channel: int) -> None:
        for _ in range(5):
            fb = self.send(f"0323{room:02x}{channel:02x}").find("feedback")
            if fb is None or fb.text == "1":
                return
        print("warning: WebControl did not report ready")

    def rooms(self):
        result = []
        try:
            room = 0
            while True:
                name = self.send(f"0203{room:02x}").findtext("raumname")
                if not name:
                    break
                channels = []
                while True:
                    xml = self.send(f"0347{room:02x}{len(channels):02x}")
                    if not xml.findtext("kanalname"):
                        break
                    channels.append(xml)
                result.append((room, name, channels))
                room += 1
        finally:
            self.send("03230000")
        return result

    def state(self, room: int, channel: int) -> ET.Element:
        self.ready(room, channel)
        return self.send(f"0431{room:02x}{channel:02x}01")

    def move(self, room: int, channel: int, position: int | None, angle: int | None) -> ET.Element:
        pos = 0xFF if position is None else max(0, min(100, position)) * 2
        ang = 0xFF if angle is None else max(0, min(254, angle))
        self.ready(room, channel)
        return self.send(f"0821{room:02x}{channel:02x}03{pos:02x}{ang:02x}ffff")


def dump(xml: ET.Element) -> str:
    return ", ".join(f"{child.tag}={child.text}" for child in xml)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("host", help="IP or hostname of the WebControl, e.g. 192.168.1.50")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list all rooms and channels incl. current state")
    for name in ("state", "watch"):
        s = sub.add_parser(name)
        s.add_argument("room", type=int)
        s.add_argument("channel", type=int)
    m = sub.add_parser("move")
    m.add_argument("room", type=int)
    m.add_argument("channel", type=int)
    m.add_argument("--position", type=int, help="0 = up/retracted, 100 = down/extended")
    m.add_argument("--angle", type=int, help="raw slat angle (see 'watch' output)")
    args = p.parse_args()

    wc = WebControl(args.host)
    if args.cmd == "list":
        for room, name, channels in wc.rooms():
            print(f"Room {room}: {name}")
            for ch, info in enumerate(channels):
                print(f"  Channel {ch}: {info.findtext('kanalname')}")
                print(f"    info : {dump(info)}")
                print(f"    state: {dump(wc.state(room, ch))}")
    elif args.cmd == "state":
        print(dump(wc.state(args.room, args.channel)))
    elif args.cmd == "move":
        print(dump(wc.move(args.room, args.channel, args.position, args.angle)))
    elif args.cmd == "watch":
        print("Move the device with the remote, Ctrl+C to stop.")
        while True:
            xml = wc.state(args.room, args.channel)
            print(f"{time.strftime('%H:%M:%S')}  moving={xml.findtext('fahrt')}  "
                  f"position={xml.findtext('position')}  winkel={xml.findtext('winkel')}")
            time.sleep(1)


if __name__ == "__main__":
    main()

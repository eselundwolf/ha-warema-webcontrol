"""Async client for the (old) Warema WMS WebControl.

The WebControl has no documented API. Its web UI talks to the box via
GET /protocol.xml?protocol=<hex>&_=<ts>, the format was reverse engineered
by the community (see https://github.com/cornim/wms_webcontrol):

    90 <counter> <cmd> <args...>

    0203 RR             room name          -> <raumname>
    0347 RR CC          channel info       -> <kanalname>
    0323 RR CC          ready check        -> <feedback>1</feedback>
    0431 RR CC 01       channel state      -> <fahrt>, <position>, <winkel>
    0821 RR CC 03 PP WW V1 V2
                        move               PP = position * 2, WW = raw angle,
                                           ff = leave unchanged

The box only handles one request at a time, so all requests are serialized.
"""

from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_DELAY = 0.3  # the box returns errors if requests come in too fast
READY_RETRIES = 5
UNCHANGED = 0xFF


class WebControlError(Exception):
    """Communication with the WebControl failed."""


@dataclass
class Channel:
    room_id: int
    channel_id: int
    room_name: str
    name: str
    info: dict[str, str | None] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.room_id}_{self.channel_id}"


@dataclass
class ChannelState:
    moving: bool
    position: int  # 0 = up/retracted, 100 = down/extended (WMS convention)
    angle: int  # raw <winkel>, 255 = not supported
    raw: dict[str, str | None]


class WebControlClient:
    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        if not host.startswith("http"):
            host = f"http://{host}"
        self._url = host.rstrip("/") + "/protocol.xml"
        self._session = session
        self._lock = asyncio.Lock()
        self._counter = 0
        self._ts = int(time.time())

    async def _send(self, cmd: str) -> ET.Element:
        async with self._lock:
            payload = f"90{self._counter:02x}{cmd}"
            self._counter = (self._counter + 1) % 256
            self._ts += 1
            try:
                async with self._session.get(
                    self._url,
                    params={"protocol": payload, "_": str(self._ts)},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise WebControlError(f"Request {payload} failed: {err}") from err
            finally:
                await asyncio.sleep(REQUEST_DELAY)
        _LOGGER.debug("%s -> %s", payload, text)
        try:
            return ET.fromstring(text)
        except ET.ParseError as err:
            raise WebControlError(f"Invalid response to {payload}: {text!r}") from err

    async def _ready(self, room: int, channel: int) -> None:
        for _ in range(READY_RETRIES):
            feedback = (await self._send(f"0323{room:02x}{channel:02x}")).findtext("feedback")
            if feedback in (None, "1"):
                return
        raise WebControlError(f"WebControl not ready for {room}/{channel}")

    async def discover(self) -> list[Channel]:
        channels: list[Channel] = []
        try:
            room = 0
            while True:
                room_name = (await self._send(f"0203{room:02x}")).findtext("raumname")
                if not room_name:
                    break
                ch = 0
                while True:
                    xml = await self._send(f"0347{room:02x}{ch:02x}")
                    name = xml.findtext("kanalname")
                    if not name:
                        break
                    channels.append(
                        Channel(room, ch, room_name, name, {c.tag: c.text for c in xml})
                    )
                    ch += 1
                room += 1
        finally:
            await self._send("03230000")
        return channels

    async def get_state(self, room: int, channel: int) -> ChannelState:
        await self._ready(room, channel)
        xml = await self._send(f"0431{room:02x}{channel:02x}01")
        raw = {c.tag: c.text for c in xml}
        try:
            return ChannelState(
                moving=raw.get("fahrt") not in (None, "0"),
                position=round(int(raw["position"]) / 2),
                angle=int(raw.get("winkel") or 255),
                raw=raw,
            )
        except (KeyError, TypeError, ValueError) as err:
            raise WebControlError(f"Unexpected state response: {raw}") from err

    async def move(
        self, room: int, channel: int, position: int | None = None, angle: int | None = None
    ) -> None:
        """Move to position (0 = up, 100 = down) and/or raw slat angle."""
        pos = UNCHANGED if position is None else max(0, min(100, position)) * 2
        ang = UNCHANGED if angle is None else max(0, min(254, angle))
        await self._ready(room, channel)
        await self._send(f"0821{room:02x}{channel:02x}03{pos:02x}{ang:02x}ffff")

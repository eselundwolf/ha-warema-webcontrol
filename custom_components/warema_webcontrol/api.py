"""Async client for the (old) Warema WMS WebControl.

The WebControl has no documented API. Its web UI talks to the box via
GET /protocol.xml?protocol=<hex>&_=<ts>, the format was reverse engineered
by the community (see https://github.com/cornim/wms_webcontrol) and checked
against the box's own web UI (script/WebControl.js):

    90 <counter> <length> <telegram> <args...>

    0203 RR             room name          -> <raumname>
    0347 RR CC          channel info       -> <kanalname>, <produkttyp>
    0323 RR CC          ask the device for its position over the radio
                                           -> responseID 51, feedback 1 = sent,
                                              feedback 0 = radio stack busy
    0431 RR CC 01       fetch that answer  -> responseID 36: <fahrt>, <position>,
                                              <winkel>; responseID 50 with
                                              feedback 0 = not there yet, ask
                                              again; responseID 52 = error
                                              (errorcode 33: device did not answer)
    0821 RR CC 03 PP WW V1 V2
                        move               PP = position * 2, WW = raw angle,
                                           ff = leave unchanged

The box only handles one request at a time, so all requests are serialized,
and a request plus its answer polling run as one transaction.
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
POLL_INTERVAL = 0.5
POLL_TIMEOUT = 7.0  # the box itself gives up after about 6 s
UNCHANGED = 0xFF

RES_POSITION = "36"
RES_ERROR = "52"


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
        self._transaction = asyncio.Lock()
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

    async def _send_radio(self, cmd: str) -> None:
        """Send a telegram that goes out over the radio.

        While the box still waits for a radio answer (up to ~6 s, e.g. from a
        device that does not answer) it rejects new telegrams with feedback 0
        ("stack busy"), so retry until it takes it.
        """
        deadline = time.monotonic() + POLL_TIMEOUT
        while True:
            feedback = (await self._send(cmd)).findtext("feedback")
            if feedback in (None, "1"):
                return
            if time.monotonic() >= deadline:
                raise WebControlError(f"WebControl busy, {cmd} was not sent")
            await asyncio.sleep(POLL_INTERVAL)

    async def discover(self) -> list[Channel]:
        async with self._transaction:
            return await self._discover()

    async def _discover(self) -> list[Channel]:
        channels: list[Channel] = []
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
                channels.append(Channel(room, ch, room_name, name, {c.tag: c.text for c in xml}))
                ch += 1
            room += 1
        return channels

    async def get_state(
        self, room: int, channel: int, timeout: float = POLL_TIMEOUT
    ) -> ChannelState:
        """Ask the device for its state and wait up to timeout seconds for the answer."""
        async with self._transaction:
            await self._send_radio(f"0323{room:02x}{channel:02x}")
            deadline = time.monotonic() + timeout
            while True:
                xml = await self._send(f"0431{room:02x}{channel:02x}01")
                response = xml.findtext("responseID")
                if response == RES_POSITION:
                    break
                if response == RES_ERROR:
                    raise WebControlError(
                        f"No answer from {room}/{channel} (error {xml.findtext('errorcode')})"
                    )
                if time.monotonic() >= deadline:
                    raise WebControlError(f"No answer from {room}/{channel} within {timeout} s")
                await asyncio.sleep(POLL_INTERVAL)
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
        async with self._transaction:
            await self._send_radio(f"0821{room:02x}{channel:02x}03{pos:02x}{ang:02x}ffff")

"""Polling coordinator for the Warema WMS WebControl."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Channel, ChannelState, WebControlClient, WebControlError
from .const import DOMAIN, FAST_SCAN_INTERVAL, FAST_SCAN_WINDOW, MOVE_START_GRACE, STALE_AFTER

_LOGGER = logging.getLogger(__name__)


class WaremaCoordinator(DataUpdateCoordinator[dict[str, ChannelState]]):
    """Polls all channels slowly, and only the active ones quickly while they move.

    Every status request goes over the WMS radio, so permanent fast polling of
    all devices would congest the network.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: WebControlClient,
        channels: list[Channel],
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.channels = {c.key: c for c in channels}
        self._slow_interval = timedelta(seconds=scan_interval)
        self._last_full_poll = 0.0
        self._active: dict[str, float] = {}  # channel key -> time of last command
        self._last_ok: dict[str, float] = {}  # channel key -> time of last answer
        self._failing: set[str] = set()

    def mark_active(self, key: str) -> None:
        self._active[key] = time.monotonic()
        self.update_interval = timedelta(seconds=FAST_SCAN_INTERVAL)

    def is_fresh(self, key: str) -> bool:
        """A channel stays available with its last state until it has not answered for a while.

        Single failed requests are common: the box only handles one client at a
        time and radio answers get lost now and then.
        """
        last = self._last_ok.get(key)
        return last is not None and time.monotonic() - last <= STALE_AFTER

    async def _async_update_data(self) -> dict[str, ChannelState]:
        now = time.monotonic()
        full = now - self._last_full_poll >= self._slow_interval.total_seconds() or not self.data
        keys = list(self.channels) if full else list(self._active)
        data = dict(self.data or {})
        errors = 0

        for key in keys:
            channel = self.channels[key]
            try:
                data[key] = await self.client.get_state(channel.room_id, channel.channel_id)
            except WebControlError as err:
                errors += 1
                if key not in self._failing:
                    _LOGGER.info("%s did not answer: %s", channel.name, err)
                self._failing.add(key)
            else:
                self._last_ok[key] = time.monotonic()
                if key in self._failing:
                    _LOGGER.info("%s answers again", channel.name)
                self._failing.discard(key)

        if keys and errors == len(keys) and not any(map(self.is_fresh, self.channels)):
            raise UpdateFailed("WebControl not reachable")
        if full:
            self._last_full_poll = now

        for key, started in list(self._active.items()):
            age = now - started
            state = data.get(key)
            # The box often still reports "not moving" right after a command,
            # so keep polling for a few seconds before trusting that.
            if age > FAST_SCAN_WINDOW or (state and not state.moving and age > MOVE_START_GRACE):
                del self._active[key]
        if not self._active:
            self.update_interval = self._slow_interval
        return data

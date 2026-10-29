"""Polling coordinator for the Warema WMS WebControl."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Channel, ChannelState, WebControlClient, WebControlError
from .const import DOMAIN, FAST_SCAN_INTERVAL, FAST_SCAN_WINDOW, MOVE_START_GRACE

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

    def mark_active(self, key: str) -> None:
        self._active[key] = time.monotonic()
        self.update_interval = timedelta(seconds=FAST_SCAN_INTERVAL)

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
                _LOGGER.debug("Update of %s failed: %s", key, err)

        if keys and errors == len(keys):
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

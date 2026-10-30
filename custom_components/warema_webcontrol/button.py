"""Preset buttons for Warema venetian blinds (Raffstoren)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WaremaConfigEntry
from .api import Channel, WebControlError
from .const import (
    CONF_TILT_CLOSED_RAW,
    CONF_TILT_SUN_RAW,
    DEFAULT_TILT_CLOSED_RAW,
    DEFAULT_TILT_SUN_RAW,
    DOMAIN,
    PRODUCT_VENETIAN_BLIND,
)
from .coordinator import WaremaCoordinator

FULLY_DOWN = 100  # WMS position


async def async_setup_entry(
    hass: HomeAssistant, entry: WaremaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    presets = {
        "sun_protection": entry.options.get(CONF_TILT_SUN_RAW, DEFAULT_TILT_SUN_RAW),
        "fully_closed": entry.options.get(CONF_TILT_CLOSED_RAW, DEFAULT_TILT_CLOSED_RAW),
    }
    async_add_entities(
        WaremaPresetButton(coordinator, entry.entry_id, channel, key, angle)
        for channel in coordinator.channels.values()
        if channel.info.get("produkttyp") == PRODUCT_VENETIAN_BLIND
        for key, angle in presets.items()
    )


class WaremaPresetButton(ButtonEntity):
    """Drives a blind fully down and sets the slats in one radio telegram.

    Position and angle have to go out together: a second telegram right after
    the first would stop the running movement.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WaremaCoordinator,
        entry_id: str,
        channel: Channel,
        key: str,
        angle: int,
    ) -> None:
        self._coordinator = coordinator
        self._channel = channel
        self._angle = angle
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}_{channel.key}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"{entry_id}_{channel.key}")})
        self._attr_icon = "mdi:sun-angle-outline" if key == "sun_protection" else "mdi:blinds"

    async def async_press(self) -> None:
        try:
            await self._coordinator.client.move(
                self._channel.room_id, self._channel.channel_id, FULLY_DOWN, self._angle
            )
        except WebControlError as err:
            raise HomeAssistantError(f"Warema command failed: {err}") from err
        self._coordinator.mark_active(self._channel.key)
        await self._coordinator.async_request_refresh()

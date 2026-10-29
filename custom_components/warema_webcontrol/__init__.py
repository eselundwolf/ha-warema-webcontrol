"""Warema WMS WebControl (old, non-pro) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WebControlClient, WebControlError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import WaremaCoordinator

PLATFORMS = [Platform.COVER]

type WaremaConfigEntry = ConfigEntry[WaremaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WaremaConfigEntry) -> bool:
    client = WebControlClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    try:
        channels = await client.discover()
    except WebControlError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = WaremaCoordinator(
        hass,
        client,
        channels,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: WaremaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WaremaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

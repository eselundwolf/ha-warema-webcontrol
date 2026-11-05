"""Config flow for the Warema WMS WebControl integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WebControlClient, WebControlError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TILT_CLOSED_RAW,
    CONF_TILT_OPEN_RAW,
    CONF_TILT_SUN_RAW,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TILT_CLOSED_RAW,
    DEFAULT_TILT_OPEN_RAW,
    DEFAULT_TILT_SUN_RAW,
    DOMAIN,
)


class WaremaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            client = WebControlClient(async_get_clientsession(self.hass), host)
            try:
                channels = await client.discover()
            except WebControlError:
                errors["base"] = "cannot_connect"
            else:
                if not channels:
                    errors["base"] = "no_devices"
                else:
                    return self.async_create_entry(
                        title=f"WMS WebControl ({host})", data={CONF_HOST: host}
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default="webcontrol.local"): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host, e.g. after the WebControl got a new IP via DHCP.

        Entities are keyed on the config entry id, not on the host, so they and
        everything that uses them (automations, dashboards) stay as they are.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if host.lower() != entry.unique_id:
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_configured()
            client = WebControlClient(async_get_clientsession(self.hass), host)
            try:
                channels = await client.discover()
            except WebControlError:
                errors["base"] = "cannot_connect"
            else:
                if not channels:
                    errors["base"] = "no_devices"
                else:
                    # Also reloads an entry stuck in "retrying setup" (the
                    # usual state after the box moved to another IP).
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=host.lower(),
                        title=f"WMS WebControl ({host})",
                        data_updates={CONF_HOST: host},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WaremaOptionsFlow()


class WaremaOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(int, vol.Range(min=10, max=3600)),
                    vol.Required(
                        CONF_TILT_OPEN_RAW,
                        default=options.get(CONF_TILT_OPEN_RAW, DEFAULT_TILT_OPEN_RAW),
                    ): vol.All(int, vol.Range(min=0, max=254)),
                    vol.Required(
                        CONF_TILT_CLOSED_RAW,
                        default=options.get(CONF_TILT_CLOSED_RAW, DEFAULT_TILT_CLOSED_RAW),
                    ): vol.All(int, vol.Range(min=0, max=254)),
                    vol.Required(
                        CONF_TILT_SUN_RAW,
                        default=options.get(CONF_TILT_SUN_RAW, DEFAULT_TILT_SUN_RAW),
                    ): vol.All(int, vol.Range(min=0, max=254)),
                }
            ),
        )

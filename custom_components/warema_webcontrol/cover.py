"""Cover entities for Warema venetian blinds (Raffstoren) and awnings (Markisen)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WaremaConfigEntry
from .api import Channel, WebControlError
from .const import (
    ANGLE_UNSUPPORTED,
    CONF_TILT_CLOSED_RAW,
    CONF_TILT_OPEN_RAW,
    DEFAULT_TILT_CLOSED_RAW,
    DEFAULT_TILT_OPEN_RAW,
    DOMAIN,
    PRODUCT_AWNING,
    PRODUCT_TYPES,
    PRODUCT_VENETIAN_BLIND,
)
from .coordinator import WaremaCoordinator

AWNING_KEYWORDS = ("markise", "awning", "terrasse")


async def async_setup_entry(
    hass: HomeAssistant, entry: WaremaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    tilt_open = entry.options.get(CONF_TILT_OPEN_RAW, DEFAULT_TILT_OPEN_RAW)
    tilt_closed = entry.options.get(CONF_TILT_CLOSED_RAW, DEFAULT_TILT_CLOSED_RAW)
    async_add_entities(
        WaremaCover(coordinator, entry.entry_id, channel, tilt_open, tilt_closed)
        for channel in coordinator.channels.values()
    )


class WaremaCover(CoordinatorEntity[WaremaCoordinator], CoverEntity):
    """One WMS channel.

    WMS counts 0 = up/retracted .. 100 = down/extended, Home Assistant counts
    0 = closed .. 100 = open. For blinds the positions are inverted (closed =
    fully down). An awning is only closed when fully retracted, so any extension
    counts as open and the WMS position is used as is.
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: WaremaCoordinator,
        entry_id: str,
        channel: Channel,
        tilt_open_raw: int,
        tilt_closed_raw: int,
    ) -> None:
        super().__init__(coordinator)
        self._channel = channel
        self._tilt_open_raw = tilt_open_raw
        self._tilt_closed_raw = tilt_closed_raw
        self._attr_unique_id = f"{entry_id}_{channel.key}"
        # The room becomes the suggested area, and Home Assistant already puts
        # the area in front of the entity ID, so it is not repeated in the name.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=channel.name,
            suggested_area=channel.room_name,
            manufacturer="Warema",
            model="WMS",
        )

        state = coordinator.data.get(channel.key)
        product = channel.info.get("produkttyp")
        if product is not None and product in PRODUCT_TYPES:
            self._has_tilt = product == PRODUCT_VENETIAN_BLIND
            is_awning = product == PRODUCT_AWNING
        else:
            # unknown product type: awnings and roller shutters report no slat angle
            self._has_tilt = state is not None and state.angle != ANGLE_UNSUPPORTED
            is_awning = any(k in channel.name.lower() for k in AWNING_KEYWORDS)
        self._inverted = not is_awning
        if self._has_tilt:
            self._attr_device_class = CoverDeviceClass.BLIND
        elif is_awning:
            self._attr_device_class = CoverDeviceClass.AWNING
            self._attr_translation_key = "awning"
        else:
            self._attr_device_class = CoverDeviceClass.SHADE

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        if self._has_tilt:
            self._attr_supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )
        self._target: int | None = None  # HA position we are moving to
        self._target_wms: int | None = None  # last WMS position sent to the box

    @property
    def _state(self):
        return self.coordinator.data.get(self._channel.key)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._state is not None
            and self.coordinator.is_fresh(self._channel.key)
        )

    def _to_ha(self, wms_position: int) -> int:
        return 100 - wms_position if self._inverted else wms_position

    _to_wms = _to_ha  # the mapping is its own inverse

    @property
    def current_cover_position(self) -> int | None:
        return None if self._state is None else self._to_ha(self._state.position)

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position == 0

    @property
    def is_opening(self) -> bool:
        return self._moving_towards(lambda target, current: target > current)

    @property
    def is_closing(self) -> bool:
        return self._moving_towards(lambda target, current: target < current)

    def _moving_towards(self, compare) -> bool:
        state = self._state
        if state is None or not state.moving or self._target is None:
            return False
        return compare(self._target, self._to_ha(state.position))

    @property
    def current_cover_tilt_position(self) -> int | None:
        state = self._state
        if not self._has_tilt or state is None or state.angle == ANGLE_UNSUPPORTED:
            return None
        span = self._tilt_open_raw - self._tilt_closed_raw
        if span == 0:
            return None
        return max(0, min(100, round((state.angle - self._tilt_closed_raw) * 100 / span)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._state
        return {
            "room_index": self._channel.room_id,
            "channel_index": self._channel.channel_id,
            "raw_angle": None if state is None else state.angle,
        }

    def _tilt_to_raw(self, tilt: int) -> int:
        span = self._tilt_open_raw - self._tilt_closed_raw
        return round(self._tilt_closed_raw + span * tilt / 100)

    async def _move(self, position: int | None = None, tilt: int | None = None) -> None:
        """position/tilt in HA convention (100 = open)."""
        wms_position = None if position is None else self._to_wms(position)
        angle = None if tilt is None else self._tilt_to_raw(tilt)
        client = self.coordinator.client
        try:
            # A tilt-only command is sent together with the position, the
            # angle-only form (position = ff) is not confirmed to work. The
            # coordinator data may be stale, so ask the box; while still moving
            # keep the last target, otherwise the blind would stop halfway.
            if wms_position is None:
                state = await client.get_state(self._channel.room_id, self._channel.channel_id)
                if state.moving and self._target_wms is not None:
                    wms_position = self._target_wms
                else:
                    wms_position = state.position
            await client.move(self._channel.room_id, self._channel.channel_id, wms_position, angle)
        except WebControlError as err:
            raise HomeAssistantError(f"Warema command failed: {err}") from err
        self._target_wms = wms_position
        if position is not None:
            self._target = position
        self.coordinator.mark_active(self._channel.key)
        await self.coordinator.async_request_refresh()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._move(position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._move(position=0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._move(position=kwargs[ATTR_POSITION])

    async def async_stop_cover(self, **kwargs: Any) -> None:
        # The protocol has no known stop command: read where we are and send that as target.
        try:
            state = await self.coordinator.client.get_state(
                self._channel.room_id, self._channel.channel_id
            )
            await self.coordinator.client.move(
                self._channel.room_id, self._channel.channel_id, state.position, None
            )
        except WebControlError as err:
            raise HomeAssistantError(f"Warema command failed: {err}") from err
        self._target = None
        self._target_wms = state.position
        self.coordinator.mark_active(self._channel.key)
        await self.coordinator.async_request_refresh()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        await self._move(tilt=100)

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        await self._move(tilt=0)

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        await self._move(tilt=kwargs[ATTR_TILT_POSITION])

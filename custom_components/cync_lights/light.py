"""Platform for light integration."""
from __future__ import annotations
from typing import Any
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for room in hub.cync_rooms:
        if not hub.cync_rooms[room]._update_callback and (
            room in config_entry.options["rooms"] or room in config_entry.options["subgroups"]
        ):
            new_devices.append(CyncRoomEntity(hub.cync_rooms[room]))

    for switch_id in hub.cync_switches:
        if (
            not hub.cync_switches[switch_id]._update_callback
            and not hub.cync_switches[switch_id].plug
            and not hub.cync_switches[switch_id].fan
            and switch_id in config_entry.options["switches"]
        ):
            new_devices.append(CyncSwitchEntity(hub.cync_switches[switch_id]))

    if new_devices:
        async_add_entities(new_devices)


class CyncRoomEntity(LightEntity):
    """Representation of a Cync Room Light Entity."""

    should_poll = False
    _attr_min_color_temp_kelvin = 2000  # Warmest (default)
    _attr_max_color_temp_kelvin = 6500  # Coldest (default)

    def __init__(self, room) -> None:
        """Initialize the light."""
        self.room = room
        self._attr_supported_color_modes = self._get_supported_color_modes()

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.room.register(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.room.reset()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{self.room.parent_room if self.room.is_subgroup else self.room.name} ({self.room.home_name})",
                )
            },
            manufacturer="Cync by Savant",
            name=f"{self.room.parent_room if self.room.is_subgroup else self.room.name} ({self.room.home_name})",
            suggested_area=f"{self.room.parent_room if self.room.is_subgroup else self.room.name}",
        )

    @property
    def icon(self) -> str | None:
        """Icon of the entity."""
        if self.room.is_subgroup:
            return "mdi:lightbulb-group-outline"
        else:
            return "mdi:lightbulb-group"

    @property
    def unique_id(self) -> str:
        """Return Unique ID string."""
        uid = "cync_room_" + "-".join(self.room.switches) + "_" + "-".join(self.room.subgroups)
        return uid

    @property
    def name(self) -> str:
        """Return the name of the room."""
        return self.room.name

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.room.power_state

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this room between 0..255."""
        return round(self.room.brightness * 255 / 100)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature of this light in Kelvin."""
        if not self.room.support_color_temp:
            return None
        # Convert room's color_temp (0-100) to Kelvin range
        return round(
            self._attr_min_color_temp_kelvin
            + (self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin)
            * (self.room.color_temp / 100)
        )

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color tuple of this light switch."""
        if not self.room.support_rgb:
            return None
        return (self.room.rgb["r"], self.room.rgb["g"], self.room.rgb["b"])

    def _get_supported_color_modes(self) -> set[ColorMode]:
        """Return list of available color modes."""
        modes: set[ColorMode] = set()
        if self.room.support_rgb:
            modes.add(ColorMode.RGB)
        if self.room.support_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes and self.room.support_brightness:
            modes.add(ColorMode.BRIGHTNESS)
        if not modes:
            modes.add(ColorMode.ONOFF)
        return modes

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the active color mode."""
        if not self.is_on:
            return None
        if self.room.support_color_temp:
            if self.room.support_rgb and self.room.rgb.get("active", False):
                return ColorMode.RGB
            return ColorMode.COLOR_TEMP
        if self.room.support_brightness:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    def _kelvin_to_percent(self, kelvin: int) -> int:
        """Convert Kelvin to percentage (0-100) based on the light's color temperature range."""
        min_k = self._attr_min_color_temp_kelvin
        max_k = self._attr_max_color_temp_kelvin
        percent = 100 * (kelvin - min_k) / (max_k - min_k)
        return round(max(0, min(100, percent)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        ct_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        if ct_kelvin is not None:
            ct_percent = self._kelvin_to_percent(ct_kelvin)
        else:
            ct_percent = None
        await self.room.turn_on(
            kwargs.get(ATTR_RGB_COLOR),
            kwargs.get(ATTR_BRIGHTNESS),
            ct_percent
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.room.turn_off()


class CyncSwitchEntity(LightEntity):
    """Representation of a Cync Switch Light Entity."""

    should_poll = False
    _attr_min_color_temp_kelvin = 2000  # Warmest (default)
    _attr_max_color_temp_kelvin = 6500  # Coldest (default)

    def __init__(self, cync_switch) -> None:
        """Initialize the light."""
        self.cync_switch = cync_switch
        self._attr_supported_color_modes = self._get_supported_color_modes()

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.cync_switch.register(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.cync_switch.reset()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.cync_switch.room.name} ({self.cync_switch.home_name})")},
            manufacturer="Cync by Savant",
            name=f"{self.cync_switch.room.name} ({self.cync_switch.home_name})",
            suggested_area=f"{self.cync_switch.room.name}",
        )

    @property
    def unique_id(self) -> str:
        """Return Unique ID string."""
        return "cync_switch_" + self.cync_switch.device_id

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return self.cync_switch.name

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.cync_switch.power_state

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this switch between 0..255."""
        return round(self.cync_switch.brightness * 255 / 100)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature of this light in Kelvin."""
        if not self.cync_switch.support_color_temp:
            return None
        # Convert switch's color_temp (0-100) to Kelvin range
        return round(
            self._attr_min_color_temp_kelvin
            + (self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin)
            * (self.cync_switch.color_temp / 100)
        )

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color tuple of this light switch."""
        if not self.cync_switch.support_rgb:
            return None
        return (self.cync_switch.rgb["r"], self.cync_switch.rgb["g"], self.cync_switch.rgb["b"])

    def _get_supported_color_modes(self) -> set[ColorMode]:
        """Return list of available color modes."""
        modes: set[ColorMode] = set()
        if self.cync_switch.support_rgb:
            modes.add(ColorMode.RGB)
        if self.cync_switch.support_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes and self.cync_switch.support_brightness:
            modes.add(ColorMode.BRIGHTNESS)
        if not modes:
            modes.add(ColorMode.ONOFF)
        return modes

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the active color mode."""
        if not self.is_on:
            return None
        if self.cync_switch.support_color_temp:
            if self.cync_switch.support_rgb and self.cync_switch.rgb.get("active", False):
                return ColorMode.RGB
            return ColorMode.COLOR_TEMP
        if self.cync_switch.support_brightness:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    def _kelvin_to_percent(self, kelvin: int) -> int:
        """Convert Kelvin to percentage (0-100) based on the light's color temperature range."""
        min_k = self._attr_min_color_temp_kelvin
        max_k = self._attr_max_color_temp_kelvin
        percent = 100 * (kelvin - min_k) / (max_k - min_k)
        return round(max(0, min(100, percent)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        ct_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        if ct_kelvin is not None:
            ct_percent = self._kelvin_to_percent(ct_kelvin)
        else:
            ct_percent = None
        await self.cync_switch.turn_on(
            kwargs.get(ATTR_RGB_COLOR),
            kwargs.get(ATTR_BRIGHTNESS),
            ct_percent
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.cync_switch.turn_off()

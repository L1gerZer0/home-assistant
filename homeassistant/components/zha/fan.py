"""Fans on Zigbee Home Automation networks."""
import functools
import logging
from typing import List, Tuple

from homeassistant.components.fan import (
    DOMAIN,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
    SPEED_OFF,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .core import typing as zha_typing
from .core.const import (
    CHANNEL_FAN,
    DATA_ZHA,
    DATA_ZHA_DISPATCHERS,
    DATA_ZHA_PLATFORM_LOADED,
    SIGNAL_ADD_ENTITIES,
    SIGNAL_ATTR_UPDATED,
    SIGNAL_ENQUEUE_ENTITY,
)
from .core.registries import ZHA_ENTITIES
from .entity import ZhaEntity

_LOGGER = logging.getLogger(__name__)

# Additional speeds in zigbee's ZCL
# Spec is unclear as to what this value means. On King Of Fans HBUniversal
# receiver, this means Very High.
SPEED_ON = "on"
# The fan speed is self-regulated
SPEED_AUTO = "auto"
# When the heated/cooled space is occupied, the fan is always on
SPEED_SMART = "smart"

SPEED_LIST = [
    SPEED_OFF,
    SPEED_LOW,
    SPEED_MEDIUM,
    SPEED_HIGH,
    SPEED_ON,
    SPEED_AUTO,
    SPEED_SMART,
]

VALUE_TO_SPEED = dict(enumerate(SPEED_LIST))
SPEED_TO_VALUE = {speed: i for i, speed in enumerate(SPEED_LIST)}
STRICT_MATCH = functools.partial(ZHA_ENTITIES.strict_match, DOMAIN)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Zigbee Home Automation fan from config entry."""
    entities = []

    async def async_discover():
        """Add enqueued entities."""
        if not entities:
            return
        to_add = [ent(*args) for ent, args in entities]
        async_add_entities(to_add, update_before_add=True)
        entities.clear()

    def async_enqueue_entity(
        entity: zha_typing.CALLABLE_T, args: Tuple[str, zha_typing.ZhaDeviceType, List]
    ):
        """Stash entity for later addition."""
        entities.append((entity, args))

    unsub = async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_discover)
    hass.data[DATA_ZHA][DATA_ZHA_DISPATCHERS].append(unsub)
    unsub = async_dispatcher_connect(
        hass, f"{SIGNAL_ENQUEUE_ENTITY}_{DOMAIN}", async_enqueue_entity
    )
    hass.data[DATA_ZHA][DATA_ZHA_DISPATCHERS].append(unsub)
    hass.data[DATA_ZHA][DATA_ZHA_PLATFORM_LOADED][DOMAIN].set()


@STRICT_MATCH(channel_names=CHANNEL_FAN)
class ZhaFan(ZhaEntity, FanEntity):
    """Representation of a ZHA fan."""

    def __init__(self, unique_id, zha_device, channels, **kwargs):
        """Init this sensor."""
        super().__init__(unique_id, zha_device, channels, **kwargs)
        self._fan_channel = self.cluster_channels.get(CHANNEL_FAN)

    async def async_added_to_hass(self):
        """Run when about to be added to hass."""
        await super().async_added_to_hass()
        await self.async_accept_signal(
            self._fan_channel, SIGNAL_ATTR_UPDATED, self.async_set_state
        )

    @callback
    def async_restore_last_state(self, last_state):
        """Restore previous state."""
        self._state = VALUE_TO_SPEED.get(last_state.state, last_state.state)

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_SET_SPEED

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        return SPEED_LIST

    @property
    def speed(self) -> str:
        """Return the current speed."""
        return self._state

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        if self._state is None:
            return False
        return self._state != SPEED_OFF

    @property
    def device_state_attributes(self):
        """Return state attributes."""
        return self.state_attributes

    @callback
    def async_set_state(self, state):
        """Handle state update from channel."""
        self._state = VALUE_TO_SPEED.get(state, self._state)
        self.async_schedule_update_ha_state()

    async def async_turn_on(self, speed: str = None, **kwargs) -> None:
        """Turn the entity on."""
        if speed is None:
            speed = SPEED_MEDIUM

        await self.async_set_speed(speed)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        await self.async_set_speed(SPEED_OFF)

    async def async_set_speed(self, speed: str) -> None:
        """Set the speed of the fan."""
        await self._fan_channel.async_set_speed(SPEED_TO_VALUE[speed])
        self.async_set_state(speed)

    async def async_update(self):
        """Attempt to retrieve on off state from the fan."""
        await super().async_update()
        if self._fan_channel:
            state = await self._fan_channel.get_attribute_value("fan_mode")
            if state is not None:
                self._state = VALUE_TO_SPEED.get(state, self._state)

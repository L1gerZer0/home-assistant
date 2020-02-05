"""
Channels module for Zigbee Home Automation.

For more details about this component, please refer to the documentation at
https://home-assistant.io/integrations/zha/
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from . import (  # noqa: F401 # pylint: disable=unused-import
    base,
    closures,
    general,
    homeautomation,
    hvac,
    lighting,
    lightlink,
    manufacturerspecific,
    measurement,
    protocol,
    security,
    smartenergy,
)
from .. import (
    const,
    device as zha_core_device,
    registries as zha_regs,
    typing as zha_typing,
)

_LOGGER = logging.getLogger(__name__)


class Channels:
    """All discovered channels of a device."""

    def __init__(self, zha_device: zha_typing.ZhaDeviceType) -> None:
        """Initialize instance."""
        self._endpoints = {}
        self._power_config = None
        self._semaphore = asyncio.Semaphore(3)
        self._unique_id = str(zha_device.ieee)
        self._zdo_channel = base.ZDOChannel(zha_device.device.endpoints[0], zha_device)
        self._zha_device = zha_device

    @property
    def endpoints(self) -> Dict[int, "EndpointChannels"]:
        """Return discover endpoints dict."""
        return self._endpoints

    @property
    def power_configuration_ch(self) -> zha_typing.ChannelType:
        """Return power configuration channel."""
        return self._power_config

    @power_configuration_ch.setter
    def power_configuration_ch(self, channel: zha_typing.ChannelType) -> None:
        """Power configuration channel setter."""
        if self._power_config is None:
            self._power_config = channel

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Return semaphore for concurrent tasks."""
        return self._semaphore

    @property
    def zdo_channel(self) -> zha_typing.ZDOChannelType:
        """Return ZDO channel."""
        return self._zdo_channel

    @property
    def zha_device(self) -> zha_typing.ZhaDeviceType:
        """Return parent zha device."""
        return self._zha_device

    @property
    def unique_id(self):
        """Return the unique id for this channel."""
        return self._unique_id

    @classmethod
    def new(cls, zha_device: zha_typing.ZhaDeviceType) -> "Channels":
        """Create new instance."""
        discovery = cls(zha_device)
        for ep_id in sorted(zha_device.device.endpoints):
            discovery.add_endpoint(ep_id)
        return discovery

    def add_endpoint(self, ep_id: int) -> None:
        """Add channels for a specific endpoint."""
        if ep_id == 0:
            return
        self._endpoints[ep_id] = EndpointChannels.new(self, ep_id)

    async def async_initialize(self, from_cache: bool = False) -> None:
        """Initialize claimed channels."""
        await self.zdo_channel.async_initialize(from_cache)
        self.zdo_channel.debug("'async_initialize' stage succeeded")
        await asyncio.gather(
            *(ep.async_initialize(from_cache) for ep in self.endpoints.values())
        )

    async def async_configure(self) -> None:
        """Configure claimed channels."""
        await self.zdo_channel.async_configure()
        self.zdo_channel.debug("'async_configure' stage succeeded")
        await asyncio.gather(*(ep.async_configure() for ep in self.endpoints.values()))

    @callback
    def async_new_entity(
        self,
        enqueue_signal: str,
        entity: zha_typing.CALLABLE_T,
        unique_id: str,
        channels: List[zha_typing.ChannelType],
    ):
        """Signal new entity addition."""
        if self.zha_device.status == zha_core_device.DeviceStatus.INITIALIZED:
            return

        self.async_send_signal(
            enqueue_signal, entity, (unique_id, self.zha_device, channels)
        )

    @callback
    def async_send_signal(self, signal: str, *args: Any) -> None:
        """Send a signal through hass dispatcher."""
        async_dispatcher_send(self.zha_device.hass, signal, *args)

    @callback
    def zha_send_event(self, event_data: Dict[str, Union[str, int]]) -> None:
        """Relay events to hass."""
        self.zha_device.hass.bus.async_fire(
            "zha_event",
            {
                const.ATTR_DEVICE_IEEE: str(self.zha_device.ieee),
                const.ATTR_UNIQUE_ID: self.unique_id,
                **event_data,
            },
        )


class EndpointChannels:
    """All channels of an endpoint."""

    def __init__(self, channels: Channels, ep_id: int):
        """Initialize instance."""
        self._all_channels = {}
        self._channels = channels
        self._claimed_channels = {}
        self._id = ep_id
        self._relay_channels = {}
        self._unique_id = f"{channels.unique_id}-{ep_id}"

    @property
    def all_channels(self) -> Dict[str, zha_typing.ChannelType]:
        """All channels of an endpoint."""
        return self._all_channels

    @property
    def claimed_channels(self) -> Dict[str, zha_typing.ChannelType]:
        """Channels in use."""
        return self._claimed_channels

    @property
    def endpoint(self) -> zha_typing.ZigpyEndpointType:
        """Return endpoint of zigpy device."""
        return self._channels.zha_device.device.endpoints[self.id]

    @property
    def id(self) -> int:
        """Return endpoint id."""
        return self._id

    @property
    def nwk(self) -> int:
        """Device NWK for logging."""
        return self._channels.zha_device.nwk

    @property
    def manufacturer(self) -> Optional[str]:
        """Return device manufacturer."""
        return self._channels.zha_device.manufacturer

    @property
    def manufacturer_code(self) -> Optional[int]:
        """Return device manufacturer."""
        return self._channels.zha_device.manufacturer_code

    @property
    def model(self) -> Optional[str]:
        """Return device model."""
        return self._channels.zha_device.model

    @property
    def relay_channels(self) -> Dict[str, zha_typing.EventRelayChannelType]:
        """Return a dict of event relay channels."""
        return self._relay_channels

    @property
    def unique_id(self):
        """Return the unique id for this channel."""
        return self._unique_id

    @classmethod
    def new(cls, channels: Channels, ep_id: int) -> "EndpointChannels":
        """Create new channels for an endpoint."""
        ep_chnls = cls(channels, ep_id)
        ep_chnls.add_all_channels()
        ep_chnls.add_relay_channels()
        return ep_chnls

    @callback
    def add_all_channels(self) -> None:
        """Create and add channels for all input clusters."""
        for cluster_id, cluster in self.endpoint.in_clusters.items():
            channel_class = zha_regs.ZIGBEE_CHANNEL_REGISTRY.get(
                cluster_id, base.AttributeListeningChannel
            )
            # really ugly hack to deal with xiaomi using the door lock cluster
            # incorrectly.
            if (
                hasattr(cluster, "ep_attribute")
                and cluster.ep_attribute == "multistate_input"
            ):
                channel_class = base.AttributeListeningChannel
            # end of ugly hack
            ch = channel_class(cluster, self)
            if ch.name == const.CHANNEL_POWER_CONFIGURATION:
                if (
                    self._channels.power_configuration_ch
                    or self._channels.zha_device.is_mains_powered
                ):
                    # on power configuration channel per device
                    continue
                self._channels.power_configuration_ch = ch

            self.all_channels[ch.id] = ch

    @callback
    def add_relay_channels(self) -> None:
        """Create relay channels for all output clusters if in the registry."""
        for cluster_id in zha_regs.EVENT_RELAY_CLUSTERS:
            cluster = self.endpoint.out_clusters.get(cluster_id)
            if cluster is not None:
                ch = base.EventRelayChannel(cluster, self)
                self.relay_channels[ch.id] = ch

    async def async_initialize(self, from_cache: bool = False) -> None:
        """Initialize claimed channels."""
        await self._execute_channel_tasks("async_initialize", from_cache)

    async def async_configure(self) -> None:
        """Configure claimed channels."""
        await self._execute_channel_tasks("async_configure")

    async def _execute_channel_tasks(self, func_name: str, *args: Any) -> None:
        """Add a throttled channel task and swallow exceptions."""

        async def _throttle(coro):
            async with self._channels.semaphore:
                return await coro

        channels = [*self.claimed_channels.values(), *self.relay_channels.values()]
        tasks = [_throttle(getattr(ch, func_name)(*args)) for ch in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ch, outcome in zip(channels, results):
            if isinstance(outcome, Exception):
                ch.warning("'%s' stage failed: %s", func_name, str(outcome))
                continue
            ch.debug("'%s' stage succeeded", func_name)

    @callback
    def async_new_entity(
        self,
        component: str,
        entity: zha_typing.CALLABLE_T,
        unique_id: str,
        channels: List[zha_typing.ChannelType],
    ):
        """Signal new entity addition."""
        enqueue_signal = f"{const.SIGNAL_ENQUEUE_ENTITY}_{component}"
        self._channels.async_new_entity(enqueue_signal, entity, unique_id, channels)

    @callback
    def async_send_signal(self, signal: str, *args: Any) -> None:
        """Send a signal through hass dispatcher."""
        self._channels.async_send_signal(signal, *args)

    @callback
    def claim_channels(self, channels: List[zha_typing.ChannelType]) -> None:
        """Claim a channel."""
        self.claimed_channels.update({ch.id: ch for ch in channels})

    @callback
    def unclaimed_channels(self) -> List[zha_typing.ChannelType]:
        """Return a list of available (unclaimed) channels."""
        claimed = set(self.claimed_channels)
        available = set(self.all_channels)
        return [self.all_channels[chan_id] for chan_id in (available - claimed)]

    @callback
    def zha_send_event(self, event_data: Dict[str, Union[str, int]]) -> None:
        """Relay events to hass."""
        self._channels.zha_send_event(
            {
                const.ATTR_UNIQUE_ID: self.unique_id,
                const.ATTR_ENDPOINT_ID: self.id,
                **event_data,
            }
        )

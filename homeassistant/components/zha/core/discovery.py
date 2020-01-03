"""
Device discovery functions for Zigbee Home Automation.

For more details about this component, please refer to the documentation at
https://home-assistant.io/integrations/zha/
"""

import collections
import logging
import typing

from zigpy.zcl.clusters.general import OnOff, PowerConfiguration

from homeassistant import const as ha_const
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from . import typing as zha_typing
from .channels import AttributeListeningChannel, EventRelayChannel, ZDOChannel
from .const import COMPONENTS, CONF_DEVICE_CONFIG, DATA_ZHA, ZHA_DISCOVERY_NEW
from .registries import (
    CHANNEL_ONLY_CLUSTERS,
    COMPONENT_CLUSTERS,
    DEVICE_CLASS,
    EVENT_RELAY_CLUSTERS,
    OUTPUT_CHANNEL_ONLY_CLUSTERS,
    REMOTE_DEVICE_TYPES,
    SINGLE_INPUT_CLUSTER_DEVICE_CLASS,
    SINGLE_OUTPUT_CLUSTER_DEVICE_CLASS,
    ZHA_ENTITIES,
    ZIGBEE_CHANNEL_REGISTRY,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_CONFIGS = {}


def update_device_overrides(config: typing.Optional[typing.Dict] = None) -> None:
    """Update module config overrides registry."""
    if config is None:
        return
    DEVICE_CONFIGS.update(config)


def async_dispatch_discovery_info(*args, **kwargs):
    pass


def async_process_endpoint(*args, **kwargs):
    pass


@callback
def _async_handle_single_cluster_matches(
    hass, endpoint, zha_device, profile_clusters, device_key, is_new_join
):
    pass


@callback
def _async_handle_channel_only_cluster_match(zha_device, cluster, is_new_join):
    """Handle a channel only cluster match."""
    _async_create_cluster_channel(cluster, zha_device, is_new_join)


@callback
def _async_handle_single_cluster_match(
    hass, zha_device, cluster, device_key, device_classes, is_new_join
):
    """Dispatch a single cluster match to a HA component."""
    component = None  # sub_component = None
    for cluster_type, candidate_component in device_classes.items():
        if isinstance(cluster_type, int):
            if cluster.cluster_id == cluster_type:
                component = candidate_component
        elif isinstance(cluster, cluster_type):
            component = candidate_component
            break

    if component is None or component not in COMPONENTS:
        return
    channels = []
    _async_create_cluster_channel(cluster, zha_device, is_new_join, channels=channels)

    cluster_key = f"{device_key}-{cluster.cluster_id}"
    discovery_info = {
        "unique_id": cluster_key,
        "zha_device": zha_device,
        "channels": channels,
        "entity_suffix": f"_{cluster.cluster_id}",
        "component": component,
    }

    return discovery_info


class Discovery:
    """All discovered channels and entities of a device."""

    def __init__(self, zha_device: zha_typing.ZhaDeviceType) -> None:
        """Initialize instance."""
        self._zha_device = zha_device

    @property
    def zha_device(self) -> zha_typing.ZhaDeviceType:
        """Return parent zha device."""
        return self._zha_device


class DiscoveryEndpoint:
    """All discovered channels and entities of an endpoint."""

    def __init__(self, discovery: Discovery, ep_id: int):
        """Initialize instance."""
        self._all_channels = {}
        self._claimed_channels = {}
        self._entities = collections.defaultdict(list)
        self._discovery = discovery
        self._id = ep_id
        self._relay_channels = {}

    @property
    def all_channels(self) -> typing.Dict[str, zha_typing.ChannelType]:
        """All channels of an endpoint."""
        return self._all_channels

    @property
    def claimed_channels(self) -> typing.Dict[str, zha_typing.ChannelType]:
        """Channels in use."""
        return self._claimed_channels

    @property
    def endpoint(self) -> zha_typing.ZigpyEndpointType:
        """Return endpoint."""
        return self._discovery.zha_device.device.endpoints[self.id]

    @property
    def entities(self) -> typing.Dict[str, typing.List[zha_typing.ZhaEntityType]]:
        """Return discovered entities."""
        return self._entities

    @property
    def relay_channels(self) -> typing.Dict[str, zha_typing.EventRelayChannelType]:
        """Return a dict of event relay channels."""
        return self._relay_channels

    @property
    def id(self) -> int:
        """Return endpoint id."""
        return self._id

    @classmethod
    def new(cls, discovery: Discovery, ep_id: int) -> "DiscoveryEndpoint":
        """Create DiscoveryEndpoint instance from endpoint."""
        r = cls(discovery, ep_id)
        r.add_all_channels()
        r.add_relay_channels()
        r.discover_entities()
        return r

    @callback
    def add_all_channels(self) -> None:
        """Create and add channels for all input clusters."""
        for cluster_id, cluster in self.endpoint.in_clusters.items():
            channel_class = ZIGBEE_CHANNEL_REGISTRY.get(
                cluster_id, AttributeListeningChannel
            )
            # really ugly hack to deal with xiaomi using the door lock cluster
            # incorrectly.
            if (
                hasattr(cluster, "ep_attribute")
                and cluster.ep_attribute == "multistate_input"
            ):
                channel_class = AttributeListeningChannel
            # end of ugly hack
            ch = channel_class(cluster, self._discovery.zha_device)
            self.all_channels[ch.id] = ch

    @callback
    def add_entity(self, component: str, entity: zha_typing.ZhaEntityType) -> None:
        """Add a ZHA entity."""
        self.entities[component].append(entity)

    @callback
    def add_relay_channels(self) -> None:
        """Create relay channels for all output clusters if in the registry."""
        for cluster_id in EVENT_RELAY_CLUSTERS:
            cluster = self.endpoint.out_clusters.get(cluster_id)
            if cluster is not None:
                ch = EventRelayChannel(cluster, self._discovery.zha_device)
                self.relay_channels[ch.id] = ch

    @callback
    def discover_entities(self) -> None:
        """Process an endpoint on a zigpy device."""

        unique_id = f"{self._discovery.zha_device.ieee}-{self.id}"

        component = DEVICE_CONFIGS.get(unique_id, {}).get(ha_const.CONF_TYPE)
        if component is None:
            ep_profile_id = self.endpoint.profile_id
            ep_device_type = self.endpoint.device_type
            component = DEVICE_CLASS[ep_profile_id].get(ep_device_type)

        if component and component in COMPONENTS:
            channels = self.unclaimed_channels()
            entity = ZHA_ENTITIES.get_entity(
                component, self._discovery.zha_device, channels
            )
            if entity is not None:
                claimed_channels = []
                self.add_entity(
                    component,
                    entity(unique_id, self._discovery.zha_device, claimed_channels),
                )

    @callback
    def claim_channels(self, channels: typing.List[zha_typing.ChannelType]) -> None:
        """Claim a channel."""
        self.claimed_channels.update({ch.id: ch for ch in channels})

    @callback
    def unclaimed_channels(self) -> typing.List[zha_typing.ChannelType]:
        """Return a list of available (unclaimed) channels."""
        claimed = set(self.claimed_channels)
        available = set(self.all_channels)
        return [self.all_channels[chan_id] for chan_id in (available - claimed)]

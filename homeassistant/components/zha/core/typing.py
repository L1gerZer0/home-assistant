"""Typing helpers for ZHA component."""

import typing

import zigpy.device
import zigpy.endpoint
import zigpy.zcl

ChannelType = "ZigbeeChannel"
EventRelayChannelType = "EventRelayChannel"
ZDOChannelType = "ZDOChannel"
ZhaDeviceType = "ZHADevice"
ZhaEntityType = "ZHAEntity"
ZhaGatewayType = "ZHAGateway"
ZigpyClusterType = zigpy.zcl.Cluster
ZigpyDeviceType = zigpy.device.Device
ZigpyEndpointType = zigpy.endpoint.Endpoint

if typing.TYPE_CHECKING:
    import homeassistant.components.zha.core.device
    import homeassistant.components.zha.core.gateway
    import homeassistant.components.zha.entity
    import homeassistant.components.zha.core.channels

    # pylint: disable=invalid-name
    ChannelType = homeassistant.components.zha.core.channels.ZigbeeChannel
    EventRelayChannelType = homeassistant.components.zha.core.channels.EventRelayChannel
    ZDOChannelType = homeassistant.components.zha.core.channels.ZDOChannel
    ZhaDeviceType = homeassistant.components.zha.core.device.ZHADevice
    ZhaEntityType = homeassistant.components.zha.entity.ZhaEntity
    ZhaGatewayType = homeassistant.components.zha.core.gateway.ZHAGateway

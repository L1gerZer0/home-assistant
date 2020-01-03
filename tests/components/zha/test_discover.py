"""Test zha device discovery."""

import asyncio
from unittest import mock

import pytest

from homeassistant.components.zha.core.channels import EventRelayChannel
import homeassistant.components.zha.core.const as zha_const
import homeassistant.components.zha.core.device as zha_core_device
import homeassistant.components.zha.core.discovery as disc
import homeassistant.components.zha.core.gateway as core_zha_gw

from .common import make_device
from .zha_devices_list import DEVICES


@pytest.fixture
def zha_device():
    """Returns a zha Device factory."""

    def _zha_device(
        endpoints=None,
        ieee="00:11:22:33:44:55:66:77",
        manufacturer="mock manufacturer",
        model="mock model",
    ):
        if endpoints is None:
            endpoints = {
                1: {"in_channels": [0, 1, 6, 8, 768], "out_channels": [0x19]},
                2: {"in_channels": [0], "out_channels": [6, 8, 0x19, 768]},
            }
        zigpy_device = make_device(endpoints, ieee, manufacturer, model)
        zha_device = zha_core_device.ZHADevice(
            mock.sentinel.hass, zigpy_device, mock.sentinel.zha_gw
        )
        return zha_device

    return _zha_device


@pytest.mark.parametrize("device", DEVICES)
async def test_devices(device, zha_gateway: core_zha_gw.ZHAGateway, hass, config_entry):
    """Test device discovery."""
    return
    zigpy_device = make_device(
        device["endpoints"],
        "00:11:22:33:44:55:66:77",
        device["manufacturer"],
        device["model"],
    )

    with mock.patch(
        "homeassistant.components.zha.core.discovery._async_create_cluster_channel",
        wraps=disc._async_create_cluster_channel,
    ) as cr_ch:
        await zha_gateway.async_device_restored(zigpy_device)
        await hass.async_block_till_done()
        tasks = [
            hass.config_entries.async_forward_entry_setup(config_entry, component)
            for component in zha_const.COMPONENTS
        ]
        await asyncio.gather(*tasks)

        await hass.async_block_till_done()

        entity_ids = hass.states.async_entity_ids()
        await hass.async_block_till_done()
        zha_entities = {
            ent for ent in entity_ids if ent.split(".")[0] in zha_const.COMPONENTS
        }

        event_channels = {
            arg[0].cluster_id
            for arg, kwarg in cr_ch.call_args_list
            if kwarg.get("channel_class") == EventRelayChannel
        }

        assert zha_entities == set(device["entities"])
        assert event_channels == set(device["event_channels"])


def test_discovery_endpoint_unclaimed_channels(channel):
    """Test unclaimed channels."""

    ch_1 = channel("on_off", 6)
    ch_2 = channel("level", 8)
    ch_3 = channel("color", 768)

    ep_discovery = disc.DiscoveryEndpoint(mock.sentinel.zha_device, mock.sentinel.ep)
    all_channels = {ch_1.id: ch_1, ch_2.id: ch_2, ch_3.id: ch_3}
    with mock.patch.dict(ep_discovery.all_channels, all_channels, clear=True):
        available = ep_discovery.unclaimed_channels()
        assert ch_1 in available
        assert ch_2 in available
        assert ch_3 in available

        ep_discovery.claimed_channels[ch_2.id] = ch_2
        available = ep_discovery.unclaimed_channels()
        assert ch_1 in available
        assert ch_2 not in available
        assert ch_3 in available

        ep_discovery.claimed_channels[ch_1.id] = ch_1
        available = ep_discovery.unclaimed_channels()
        assert ch_1 not in available
        assert ch_2 not in available
        assert ch_3 in available

        ep_discovery.claimed_channels[ch_3.id] = ch_3
        available = ep_discovery.unclaimed_channels()
        assert ch_1 not in available
        assert ch_2 not in available
        assert ch_3 not in available


@mock.patch("disc.DiscoveryEndpoint.add_all_channels")
@mock.patch("disc.DiscoveryEndpoint.add_relay_channels")
@mock.patch("disc.DiscoveryEndpoint.discover_entities")
def test_discovery_endpoint_new(m1, m2, m3, zha_device):
    """Test discover endpoint class method."""
    zha_dev = zha_device()
    dis_ep = disc.DiscoveryEndpoint.new(zha_dev, 2)


def test_discovery_endpoint_add_relay_channels():
    """Test adding of relay channels"""
    pass

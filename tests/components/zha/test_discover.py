"""Test zha device discovery."""

import asyncio
from unittest import mock

import pytest

from homeassistant.components.zha.core.channels import EventRelayChannel
import homeassistant.components.zha.core.const as zha_const
import homeassistant.components.zha.core.device as zha_core_device
import homeassistant.components.zha.core.discovery as disc
import homeassistant.components.zha.core.gateway as core_zha_gw
import homeassistant.components.zha.core.registries as zha_regs

from .common import make_device
from .zha_devices_list import DEVICES


@pytest.fixture
def zha_device(hass, zha_gateway):
    """Returns a zha Device factory."""

    def _zha_device(
        endpoints=None,
        ieee="00:11:22:33:44:55:66:77",
        manufacturer="mock manufacturer",
        model="mock model",
    ):
        if endpoints is None:
            endpoints = {
                1: {
                    "in_clusters": [0, 1, 6, 8, 768],
                    "out_clusters": [0x19],
                    "device_type": 0x0105,
                },
                2: {
                    "in_clusters": [0],
                    "out_clusters": [6, 8, 0x19, 768],
                    "device_type": 0x0810,
                },
            }
        zigpy_device = make_device(endpoints, ieee, manufacturer, model)
        zha_device = zha_core_device.ZHADevice(hass, zigpy_device, zha_gateway)
        return zha_device

    return _zha_device


@pytest.fixture
def zha_device_light_on_off(zha_device):
    """ON/Off light."""
    ep_data = {"in_clusters": [0, 1, 6], "out_clusters": [0x19], "device_type": 0x0100}
    return zha_device({2: ep_data})


@pytest.fixture
def zha_device_light_dimmable(zha_device):
    """Dimmable light."""
    ep_data = {
        "in_clusters": [0, 1, 6, 8],
        "out_clusters": [0x19],
        "device_type": 0x0101,
    }
    return zha_device({2: ep_data})


@pytest.fixture
def zha_device_light_color(zha_device):
    """Color dimmable light."""
    ep_data = {
        "in_clusters": [0, 1, 6, 8, 768],
        "out_clusters": [0x19],
        "device_type": 0x0102,
    }
    return zha_device({2: ep_data})


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

    ch_1 = channel(zha_const.CHANNEL_ON_OFF, 6)
    ch_2 = channel(zha_const.CHANNEL_LEVEL, 8)
    ch_3 = channel(zha_const.CHANNEL_COLOR, 768)

    ep_discovery = disc.DiscoveryEndpoint(mock.sentinel.disc, mock.sentinel.ep)
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


@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.discover_entities"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_relay_channels"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_all_channels"
)
def test_discovery_endpoint_new(m1, m2, m3, zha_device):
    """Test discover endpoint class method."""
    zha_dev = zha_device()
    m1.reset_mock()
    m2.reset_mock()
    m3.reset_mock()
    disc_ep = disc.DiscoveryEndpoint.new(zha_dev, 1)
    assert isinstance(disc_ep, disc.DiscoveryEndpoint)
    assert m1.call_count == 1
    assert m2.call_count == 1
    assert m3.call_count == 1


def test_discovery_endpoint_add_relay_channels(zha_device):
    """Test adding of relay channels"""
    zha_dev = zha_device()
    discovery = disc.Discovery(zha_dev)
    disc_ep = disc.DiscoveryEndpoint(discovery, 2)

    assert not disc_ep.relay_channels

    disc_ep.add_relay_channels()
    assert len(disc_ep.relay_channels) == 3
    assert "2:0x0006" in disc_ep.relay_channels
    assert "2:0x0008" in disc_ep.relay_channels
    assert "2:0x0300" in disc_ep.relay_channels


def test_discovery_endpoint_claim_channels(channel):
    """Test channel claiming."""

    ch_1 = channel(zha_const.CHANNEL_ON_OFF, 6)
    ch_2 = channel(zha_const.CHANNEL_LEVEL, 8)
    ch_3 = channel(zha_const.CHANNEL_COLOR, 768)

    ep_discovery = disc.DiscoveryEndpoint(mock.sentinel.disc, mock.sentinel.ep)
    all_channels = {ch_1.id: ch_1, ch_2.id: ch_2, ch_3.id: ch_3}
    with mock.patch.dict(ep_discovery.all_channels, all_channels, clear=True):
        assert ch_1.id not in ep_discovery.claimed_channels
        assert ch_2.id not in ep_discovery.claimed_channels
        assert ch_3.id not in ep_discovery.claimed_channels

        ep_discovery.claim_channels([ch_2])
        assert ch_1.id not in ep_discovery.claimed_channels
        assert ch_2.id in ep_discovery.claimed_channels
        assert ep_discovery.claimed_channels[ch_2.id] is ch_2
        assert ch_3.id not in ep_discovery.claimed_channels

        ep_discovery.claim_channels([ch_3, ch_1])
        assert ch_1.id in ep_discovery.claimed_channels
        assert ep_discovery.claimed_channels[ch_1.id] is ch_1
        assert ch_2.id in ep_discovery.claimed_channels
        assert ep_discovery.claimed_channels[ch_2.id] is ch_2
        assert ch_3.id in ep_discovery.claimed_channels
        assert ep_discovery.claimed_channels[ch_3.id] is ch_3
        assert "1:0x0300" in ep_discovery.claimed_channels


@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.discover_by_cluster_id"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_relay_channels"
)
def test_discovery_endpoint_by_device_type(m1, m2, zha_device_light_color):
    """Test entity discovery."""

    get_entity_mock = mock.MagicMock()
    entity_mock = mock.MagicMock()
    get_entity_mock.return_value = (
        entity_mock,
        zha_regs.MatchRule(
            channel_names="on_off", aux_channels={"level", "light_color"}
        ),
    )
    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        discovery = disc.Discovery(zha_device_light_color)
        disc_ep = disc.DiscoveryEndpoint.new(discovery, 2)
    assert "2:0x0006" in disc_ep.all_channels
    assert "2:0x0008" in disc_ep.all_channels
    assert "2:0x0300" in disc_ep.all_channels
    assert disc_ep.claimed_channels
    assert "2:0x0006" in disc_ep.claimed_channels
    assert "2:0x0008" in disc_ep.claimed_channels
    assert "2:0x0300" in disc_ep.claimed_channels
    assert disc_ep.entities[zha_const.LIGHT][0] is entity_mock.return_value


@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.discover_by_cluster_id"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_relay_channels"
)
def test_discovery_endpoint_by_device_type_dimmable(m1, m2, zha_device_light_dimmable):
    """Test entity discovery."""

    get_entity_mock = mock.MagicMock()
    entity_mock = mock.MagicMock()
    get_entity_mock.return_value = (
        entity_mock,
        zha_regs.MatchRule(
            channel_names="on_off", aux_channels={"level", "light_color"}
        ),
    )
    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        discovery = disc.Discovery(zha_device_light_dimmable)
        disc_ep = disc.DiscoveryEndpoint.new(discovery, 2)
    assert "2:0x0006" in disc_ep.all_channels
    assert "2:0x0008" in disc_ep.all_channels
    assert "2:0x0300" not in disc_ep.all_channels
    assert disc_ep.claimed_channels
    assert "2:0x0006" in disc_ep.claimed_channels
    assert "2:0x0008" in disc_ep.claimed_channels
    assert "2:0x0300" not in disc_ep.claimed_channels
    assert disc_ep.entities[zha_const.LIGHT][0] is entity_mock.return_value


@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.discover_by_cluster_id"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_relay_channels"
)
def test_discovery_endpoint_by_device_type_on_off(m1, m2, zha_device_light_on_off):
    """Test entity discovery."""

    get_entity_mock = mock.MagicMock()
    entity_mock = mock.MagicMock()
    get_entity_mock.return_value = (
        entity_mock,
        zha_regs.MatchRule(
            channel_names="on_off", aux_channels={"level", "light_color"}
        ),
    )
    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        discovery = disc.Discovery(zha_device_light_on_off)
        disc_ep = disc.DiscoveryEndpoint.new(discovery, 2)
    assert "2:0x0006" in disc_ep.all_channels
    assert "2:0x0008" not in disc_ep.all_channels
    assert "2:0x0300" not in disc_ep.all_channels
    assert disc_ep.claimed_channels
    assert "2:0x0006" in disc_ep.claimed_channels
    assert "2:0x0008" not in disc_ep.claimed_channels
    assert "2:0x0300" not in disc_ep.claimed_channels
    assert disc_ep.entities[zha_const.LIGHT][0] is entity_mock.return_value


@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.discover_by_cluster_id"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_relay_channels"
)
def test_discovery_endpoint_by_device_type_override(m1, m2, zha_device_light_color):
    """Test entity discovery with override to switch component."""

    get_entity_mock = mock.MagicMock()
    entity_mock = mock.MagicMock()
    get_entity_mock.return_value = (
        entity_mock,
        zha_regs.MatchRule(channel_names=zha_const.CHANNEL_ON_OFF),
    )
    device_key = f"{zha_device_light_color.ieee}-2"
    device_overrides = {device_key: {"type": "switch"}}

    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        with mock.patch.dict(disc.DEVICE_CONFIGS, device_overrides, clear=True):
            discovery = disc.Discovery(zha_device_light_color)
            disc_ep = disc.DiscoveryEndpoint.new(discovery, 2)
    assert "2:0x0006" in disc_ep.all_channels
    assert "2:0x0008" in disc_ep.all_channels
    assert "2:0x0300" in disc_ep.all_channels
    assert disc_ep.claimed_channels
    assert "2:0x0006" in disc_ep.claimed_channels
    assert "2:0x0008" not in disc_ep.claimed_channels
    assert "2:0x0300" not in disc_ep.claimed_channels
    assert disc_ep.entities[zha_const.SWITCH][0] is entity_mock.return_value


@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.discover_by_cluster_id"
)
@mock.patch(
    "homeassistant.components.zha.core.discovery.DiscoveryEndpoint.add_relay_channels"
)
def test_discovery_endpoint_by_device_type_wrong_override(
    m1, m2, zha_device_light_color
):
    """Test entity discovery with override to wrong component."""

    get_entity_mock = mock.MagicMock()
    get_entity_mock.return_value = None, None

    device_key = f"{zha_device_light_color.ieee}-2"
    device_overrides = {device_key: {"type": "fan"}}

    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        with mock.patch.dict(disc.DEVICE_CONFIGS, device_overrides, clear=True):
            discovery = disc.Discovery(zha_device_light_color)
            disc_ep = disc.DiscoveryEndpoint.new(discovery, 2)
    assert "2:0x0006" in disc_ep.all_channels
    assert "2:0x0008" in disc_ep.all_channels
    assert "2:0x0300" in disc_ep.all_channels
    assert not disc_ep.claimed_channels
    assert not disc_ep.entities[zha_const.FAN]

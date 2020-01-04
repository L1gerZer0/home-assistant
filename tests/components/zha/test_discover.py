"""Test zha device discovery."""

import asyncio
from unittest import mock

import pytest

import homeassistant.components.zha.core.channels as zha_channels
import homeassistant.components.zha.core.const as zha_const
import homeassistant.components.zha.core.device as zha_core_device
import homeassistant.components.zha.core.discovery as disc
import homeassistant.components.zha.core.gateway as core_zha_gw
import homeassistant.components.zha.core.registries as zha_regs
import homeassistant.components.zha.light as zha_light
import homeassistant.components.zha.lock as zha_lock  # noqa: F401 pylint: disable=unused-imoort
import homeassistant.components.zha.sensor as zha_sensor

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
                    "in_clusters": [0, 1, 8, 768],
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
            if kwarg.get("channel_class") == zha_channels.EventRelayChannel
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


@pytest.fixture
def discovery_endpoint():
    """Discovery endpoint fixture."""

    def _disc_ep(zha_device, ep_id=1):
        discovery = disc.Discovery(zha_device)
        return disc.DiscoveryEndpoint(discovery, ep_id)

    return _disc_ep


@pytest.mark.parametrize(
    "cluster_id, channel_name, component",
    [
        (1026, zha_const.CHANNEL_TEMPERATURE, zha_const.SENSOR),
        (
            zha_regs.SMARTTHINGS_ACCELERATION_CLUSTER,
            zha_const.CHANNEL_ACCELEROMETER,
            zha_const.BINARY_SENSOR,
        ),
        (6, zha_const.CHANNEL_ON_OFF, zha_const.SWITCH),
        (0x202, zha_const.CHANNEL_FAN, zha_const.FAN),
    ],
)
def test_discovery_endpoint_by_cluster_id(
    cluster_id, channel_name, component, discovery_endpoint, zha_device
):
    """Test single cluster discovery."""

    ep_data = {
        "device_type": 24321,
        "in_clusters": [cluster_id],
        "out_clusters": [],
        "profile_id": 260,
    }
    device = zha_device({2: ep_data})

    get_entity_mock = mock.MagicMock()
    entity_mock = mock.MagicMock()
    get_entity_mock.return_value = (
        entity_mock,
        zha_regs.MatchRule(channel_names=channel_name),
    )
    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        disc_ep = discovery_endpoint(device, 2)
        disc_ep.add_all_channels()
        disc_ep.handle_on_off_output_cluster_exception = mock.MagicMock()
        disc_ep.discover_by_cluster_id()

    assert disc_ep.handle_on_off_output_cluster_exception.call_count == 1
    ch_id = f"2:0x{cluster_id:04x}"

    assert ch_id in disc_ep.all_channels
    assert len(disc_ep.all_channels) == 1

    assert len(disc_ep.claimed_channels) == 1
    assert ch_id in disc_ep.claimed_channels

    assert disc_ep.entities[component][0] is entity_mock.return_value
    assert len(disc_ep.entities[component]) == 1


@pytest.mark.parametrize(
    "cluster_id, channel_name, device_type, component, matched",
    [
        (6, zha_const.CHANNEL_ON_OFF, 1, zha_const.BINARY_SENSOR, True),
        (6, zha_const.CHANNEL_ON_OFF, 6, zha_const.BINARY_SENSOR, False),
    ],
)
def test_discovery_endpoint_out_clusters(
    cluster_id,
    channel_name,
    device_type,
    component,
    matched,
    discovery_endpoint,
    zha_device,
):
    """Test single cluster discovery on_off output cluster handling as entity."""

    ep_data = {
        "device_type": device_type,
        "in_clusters": [],
        "out_clusters": [cluster_id],
        "profile_id": 260,
    }
    device = zha_device({2: ep_data})

    get_entity_mock = mock.MagicMock()
    entity_mock = mock.MagicMock()
    get_entity_mock.return_value = (
        entity_mock,
        zha_regs.MatchRule(channel_names=channel_name),
    )
    with mock.patch(
        "homeassistant.components.zha.core.registries.ZHA_ENTITIES.get_entity",
        get_entity_mock,
    ):
        disc_ep = discovery_endpoint(device, 2)
        disc_ep.add_all_channels()
        disc_ep.handle_on_off_output_cluster_exception()

    ch_id = f"2:0x{cluster_id:04x}"

    assert not disc_ep.all_channels

    if matched:
        assert len(disc_ep.claimed_channels) == 1
        assert ch_id in disc_ep.claimed_channels
        assert disc_ep.entities[component][0] is entity_mock.return_value
        assert len(disc_ep.entities[component]) == 1
    else:
        assert not disc_ep.claimed_channels
        assert not disc_ep.entities[component]


@pytest.fixture
def discovery_endpoint_ch():
    """Discovery endpoint fixture for channel/entity dedup."""

    def _disc_ep(channels, ep_id):
        disc_ep_mock = mock.MagicMock(spec=disc.DiscoveryEndpoint)
        disc_ep_mock.all_channels = {ch.id: ch for ch in channels}
        disc_ep_mock.claimed_channels = {ch.id: ch for ch in channels}
        disc_ep_mock.entities = {
            zha_const.SENSOR: [
                mock.MagicMock(spec=zha_sensor.Battery)
                if ch.name == zha_const.CHANNEL_POWER_CONFIGURATION
                else mock.MagicMock(spec=zha_sensor.Sensor)
                for ch in channels
            ]
        }
        return disc_ep_mock

    return _disc_ep


def test_discovery_dedup(channel, discovery_endpoint_ch):
    """Test Discovery class PowerConfiguration channel deduplication."""

    ch_1_1 = channel(zha_const.CHANNEL_POWER_CONFIGURATION, 1, endpoint_id=1)
    ch_1_6 = channel(zha_const.CHANNEL_ON_OFF, 6, endpoint_id=1)
    ch_1_8 = channel(zha_const.CHANNEL_LEVEL, 8, endpoint_id=1)
    ch_2_1 = channel(zha_const.CHANNEL_POWER_CONFIGURATION, 1, endpoint_id=2)
    ch_2_6 = channel(zha_const.CHANNEL_ON_OFF, 6, endpoint_id=2)
    ch_2_8 = channel(zha_const.CHANNEL_LEVEL, 8, endpoint_id=2)
    ch_3_1 = channel(zha_const.CHANNEL_POWER_CONFIGURATION, 1, endpoint_id=3)
    ch_3_8 = channel(zha_const.CHANNEL_LEVEL, 8, endpoint_id=3)

    disc_ep_1 = discovery_endpoint_ch([ch_1_1, ch_1_6, ch_1_8], ep_id=1)
    disc_ep_2 = discovery_endpoint_ch([ch_2_1, ch_2_6, ch_2_8], ep_id=2)
    disc_ep_3 = discovery_endpoint_ch([ch_3_1, ch_3_8], ep_id=3)
    with mock.patch(
        "homeassistant.components.zha.core.channels.ZDOChannel"
    ) as zdo_mock:
        zdo_mock.return_value.id = zha_const.CHANNEL_ZDO
        discovery = disc.Discovery(mock.MagicMock())
    discovery._endpoints = {1: disc_ep_1, 2: disc_ep_2, 3: disc_ep_3}

    # we should have only one POWER_CONFIGURATION channel
    channels = discovery.claimed_channels
    assert len(channels) == 7
    assert zha_const.CHANNEL_ZDO in channels
    assert ch_1_1.id in channels
    assert ch_1_6.id in channels
    assert ch_1_8.id in channels
    assert ch_2_6.id in channels
    assert ch_2_8.id in channels
    assert ch_3_8.id in channels

    # we should have only one Battery sensor entity
    entities = discovery.entities[zha_const.SENSOR]
    assert len(entities) == 6
    assert len([ent for ent in entities if isinstance(ent, zha_sensor.Battery)]) == 1


@mock.patch("homeassistant.components.zha.light.Light", spec=zha_light.Light)
@mock.patch("homeassistant.components.zha.sensor.Sensor", spec=zha_sensor.Sensor)
def test_discovery_new(m1, m2, zha_device):
    """Test new class method."""
    ep_1 = {
        "device_type": 1,
        "in_clusters": [1, 6, 8, 768, 0x101],
        "out_clusters": [0x19],
        "profile_id": 260,
    }
    ep_2 = {
        "in_clusters": [1, 6, 8],
        "out_clusters": [0x19, 768],
        "device_type": 0x0102,
        "profile_id": 260,
    }
    ep_3 = {
        "in_clusters": [],
        "out_clusters": [6, 8, 768],
        "device_type": 0x0002,
        "profile_id": 260,
    }
    device = zha_device({1: ep_1, 2: ep_2, 3: ep_3})

    discovery = disc.Discovery.new(device)

    assert discovery.relay_channels
    assert len(discovery.relay_channels) == 4
    assert "2:0x0300" in discovery.relay_channels
    assert "3:0x0006" in discovery.relay_channels
    assert "3:0x0008" in discovery.relay_channels
    assert "3:0x0300" in discovery.relay_channels

    assert len(discovery.claimed_channels) == 5
    assert zha_const.CHANNEL_ZDO in discovery.claimed_channels
    assert "1:0x0001" in discovery.claimed_channels
    assert "2:0x0006" in discovery.claimed_channels
    assert "2:0x0008" in discovery.claimed_channels

    assert len(discovery.entities) == 3
    assert zha_const.SENSOR in discovery.entities
    assert zha_const.LIGHT in discovery.entities
    assert zha_const.LOCK in discovery.entities
    assert len(discovery.entities[zha_const.LIGHT]) == 1
    assert len(discovery.entities[zha_const.LOCK]) == 1
    assert len(discovery.entities[zha_const.SENSOR]) == 1

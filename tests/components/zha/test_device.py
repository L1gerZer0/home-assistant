"""Test ZHA Device."""
from unittest import mock

import homeassistant.components.zha.core.const as zha_const
import homeassistant.components.zha.core.discovery as zha_disc


async def test_zha_device_config_init(channel, zha_device):
    """Test zha device channel configuration is called once."""

    ep_data = {
        "in_clusters": [1, 6, 8, 768],
        "out_clusters": [0x19],
        "device_type": 0x0102,
    }

    ch_1 = channel(zha_const.CHANNEL_ON_OFF, 6)
    ch_2 = channel(zha_const.CHANNEL_LEVEL, 8)
    ch_3 = channel(zha_const.CHANNEL_COLOR, 768)
    rch_1 = channel(zha_const.CHANNEL_ON_OFF, 6)
    rch_2 = channel(zha_const.CHANNEL_LEVEL, 8)
    rch_3 = channel(zha_const.CHANNEL_COLOR, 768)

    mock_disc = mock.MagicMock(spec=zha_disc.Discovery)
    mock_disc.new.return_value.claimed_channels = {
        ch.id: ch for ch in (ch_1, ch_2, ch_3)
    }
    mock_disc.new.return_value.relay_channels = {
        ch.id: ch for ch in (rch_1, rch_2, rch_3)
    }

    with mock.patch("homeassistant.components.zha.core.discovery.Discovery", mock_disc):
        device = zha_device({1: ep_data})
        await device.async_configure()

        assert ch_1.async_configure.call_count == 1
        assert ch_2.async_configure.call_count == 1
        assert ch_3.async_configure.call_count == 1
        assert rch_1.async_configure.call_count == 1
        assert rch_2.async_configure.call_count == 1
        assert rch_3.async_configure.call_count == 1

        assert ch_1.async_initialize.call_count == 0
        assert ch_2.async_initialize.call_count == 0
        assert ch_3.async_initialize.call_count == 0
        assert rch_1.async_initialize.call_count == 0
        assert rch_2.async_initialize.call_count == 0
        assert rch_3.async_initialize.call_count == 0

        await device.async_initialize(from_cache=False)
        assert ch_1.async_initialize.call_count == 1
        assert ch_2.async_initialize.call_count == 1
        assert ch_3.async_initialize.call_count == 1
        assert rch_1.async_initialize.call_count == 1
        assert rch_2.async_initialize.call_count == 1
        assert rch_3.async_initialize.call_count == 1

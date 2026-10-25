"""Select entity for Extron CrossPoint representing active source presets."""

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_SOURCES,
    CONF_SOURCE_INPUT,
    CONF_SOURCE_NAME,
    CONF_SOURCE_VIDEO_OUT,
    CONF_SOURCE_AUDIO_OUT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Extron Source Preset select entity."""
    data = hass.data[DOMAIN]
    client = data["client"]
    conf = data["config"]

    sources_conf = conf.get(CONF_SOURCES, {})
    if not sources_conf:
        _LOGGER.warning("No sources/presets defined for extron_crosspoint in configuration.yaml")
        return

    async_add_entities([ExtronSourcePresetSelect(client, sources_conf)])


class ExtronSourcePresetSelect(SelectEntity):
    """Represents the active gaming source on the Extron CrossPoint."""

    def __init__(self, client, sources_conf: dict):
        self._client = client
        self._sources = sources_conf
        self._attr_name = "Extron Active Source"
        self._attr_unique_id = "extron_active_source"
        self._attr_icon = "mdi:gamepad-variant"

        # Build lookup tables
        # Display name -> preset dictionary
        self._name_to_source = {}
        # Physical Input number -> Display name
        self._input_to_name = {}

        options = []
        for key, s_data in self._sources.items():
            name = s_data.get(CONF_SOURCE_NAME, key)
            self._name_to_source[name] = s_data
            self._input_to_name[s_data[CONF_SOURCE_INPUT]] = name
            options.append(name)

        self._attr_options = options
        self._attr_current_option = None

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        """Register callback for real-time front-panel tie updates."""
        self._client.register_callback(self._handle_tie_update)

    @callback
    def _handle_tie_update(self, out_num: int, in_num: int, plane: str) -> None:
        """Update selected source if an Extron front-panel button was pressed."""
        # Check if the incoming tie matches one of our defined sources
        if in_num in self._input_to_name:
            source_name = self._input_to_name[in_num]
            source_cfg = self._name_to_source[source_name]

            # If the tie event matches this source's designated video or audio output
            if out_num in (source_cfg[CONF_SOURCE_VIDEO_OUT], source_cfg[CONF_SOURCE_AUDIO_OUT]):
                self._attr_current_option = source_name
                self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Route both video and audio independently based on preset definition."""
        source = self._name_to_source.get(option)
        if not source:
            return

        in_num = source[CONF_SOURCE_INPUT]
        video_out = source[CONF_SOURCE_VIDEO_OUT]
        audio_out = source[CONF_SOURCE_AUDIO_OUT]

        _LOGGER.debug(
            "Activating preset '%s': In %s -> Video Out %s, Audio Out %s",
            option,
            in_num,
            video_out,
            audio_out,
        )

        if video_out == audio_out:
            # Video and Audio are going to the exact same output: route jointly (!)
            await self._client.route(in_num, video_out, tie_type="all")
        else:
            # Coordinated breakaway routing:
            # 1. Route video to video_out (%)
            await self._client.route(in_num, video_out, tie_type="video")
            # 2. Route audio to audio_out ($)
            await self._client.route(in_num, audio_out, tie_type="audio")

        self._attr_current_option = option
        self.async_write_ha_state()

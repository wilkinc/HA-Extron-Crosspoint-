"""Select entities for Extron CrossPoint outputs using push updates."""

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.core import callback

from .const import DOMAIN, CONF_INPUTS, CONF_OUTPUTS

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Extron output select entities."""
    data = hass.data[DOMAIN]
    client = data["client"]
    conf = data["config"]

    inputs_map = conf[CONF_INPUTS]
    outputs_map = conf[CONF_OUTPUTS]

    entities = []
    for out_num, out_name in outputs_map.items():
        entities.append(ExtronOutputSelect(client, out_num, out_name, inputs_map))

    async_add_entities(entities)


class ExtronOutputSelect(SelectEntity):
    """Represents a physical output on the Extron CrossPoint."""

    def __init__(self, client, out_num: int, out_name: str, inputs_map: dict):
        self._client = client
        self._out_num = out_num
        self._attr_name = f"Extron {out_name}"
        self._attr_unique_id = f"extron_output_{out_num}"
        self._inputs_map = inputs_map
        self._name_to_input = {v: k for k, v in inputs_map.items()}
        self._attr_options = list(inputs_map.values())
        self._attr_current_option = None

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        self._client.register_callback(self._out_num, self._handle_tie_update)

    @callback
    def _handle_tie_update(self, in_num: int) -> None:
        if in_num in self._inputs_map:
            self._attr_current_option = self._inputs_map[in_num]
        elif in_num == 0:
            self._attr_current_option = None
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        in_num = self._name_to_input.get(option)
        if in_num is not None:
            await self._client.route(in_num, self._out_num, tie_type="all")
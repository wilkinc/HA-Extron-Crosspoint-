"""The Extron CrossPoint integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .extron import ExtronClient

PLATFORMS = ["select"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Extron CrossPoint from configuration.yaml."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    host = conf[CONF_HOST]
    port = conf.get(CONF_PORT, 23)

    client = ExtronClient(host, port)
    hass.data[DOMAIN] = {
        "client": client,
        "config": conf,
    }

    await client.start()

    hass.async_create_task(
        discovery.async_load_platform(hass, "select", DOMAIN, {}, config)
    )
    return True
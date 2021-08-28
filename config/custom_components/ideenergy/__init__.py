"""The i-de.es sensor integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

import ideenergy


# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
PLATFORMS = ["sensor"]
SCAN_INTERVAL = timedelta(seconds=10)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up i-de.es sensor from a config entry."""

    sess = async_get_clientsession(hass)
    hass.data[DOMAIN] = hass.data.get(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = ideenergy.Client(sess, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], logger=_LOGGER.getChild('client'))
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

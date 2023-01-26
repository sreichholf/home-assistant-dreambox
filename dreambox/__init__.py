"""The Dreambox integration."""
from voluptuous.schema_builder import Schema
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv

from dreamboxapi.api import DreamboxApi

import asyncio

from .const import (
    CONF_CONNECTIONS,
    DEFAULT_PICON_PATH,
    DOMAIN,
    PLATFORMS,
)

from homeassistant.const import (
    CONF_DEVICES,
    CONF_HOST,
    CONF_PATH,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Dreambox component."""
    hass.data.setdefault(DOMAIN, {CONF_CONNECTIONS: {}, CONF_DEVICES: set()})
    if DOMAIN in config:
        for entry_config in config[DOMAIN][CONF_DEVICES]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": "import"}, data=entry_config
                )
            )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dreambox from a config entry."""
    _async_import_options_from_data_if_missing(hass, entry)
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    piconpath = entry.options[CONF_PATH]
    ssl = entry.data[CONF_SSL]
    api = DreamboxApi(
        host=host,
        port=port,
        user=username,
        password=password,
        https=ssl,
        piconpath=piconpath,
    )
    hass.data[DOMAIN][CONF_CONNECTIONS][entry.entry_id] = api
    await hass.async_add_executor_job(api.get_deviceinfo)

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


@callback
def _async_import_options_from_data_if_missing(hass, entry):
    options = dict(entry.options)
    if CONF_PATH not in entry.options:
        options[CONF_PATH] = entry.data.get(CONF_PATH, DEFAULT_PICON_PATH)
        hass.config_entries.async_update_entry(entry, options=options)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN][CONF_CONNECTIONS].pop(entry.entry_id)

    return unload_ok

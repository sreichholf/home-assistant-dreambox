"""The Dreambox integration."""

from dreamboxapi.api import DreamboxApi
from homeassistant.const import (
    CONF_DEVICES,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PATH,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback

from .const import DEFAULT_PICON_PATH, DOMAIN, PLATFORMS
from .coordinator import DreamboxConfigEntry, DreamboxCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Dreambox component."""
    if DOMAIN in config:
        for entry_config in config[DOMAIN][CONF_DEVICES]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": "import"}, data=entry_config
                )
            )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DreamboxConfigEntry) -> bool:
    """Set up Dreambox from a config entry."""
    _async_import_options_from_data_if_missing(hass, entry)

    api = DreamboxApi(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        user=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        https=entry.data[CONF_SSL],
        piconpath=entry.options[CONF_PATH],
    )
    coordinator = DreamboxCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.async_shutdown()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


@callback
def _async_import_options_from_data_if_missing(hass, entry):
    options = dict(entry.options)
    if CONF_PATH not in entry.options:
        options[CONF_PATH] = entry.data.get(CONF_PATH, DEFAULT_PICON_PATH)
        hass.config_entries.async_update_entry(entry, options=options)


async def async_unload_entry(hass: HomeAssistant, entry: DreamboxConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

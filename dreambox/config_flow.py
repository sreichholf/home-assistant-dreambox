from urllib.parse import urlparse

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from dreamboxapi.api import AuthenticationFailed, DreamboxApi
from homeassistant import config_entries
from homeassistant.components import ssdp
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PATH,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import callback

from .const import (
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_PICON_PATH,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_USERNAME,
    DOMAIN,
)

DATA_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
        vol.Optional(CONF_PATH, default=DEFAULT_PICON_PATH): cv.string,
    }
)

RESULT_CANNOT_CONNECT = "cannot_connect"
RESULT_INVALID_AUTH = "invalid_auth"
RESULT_SUCCESS = "success"


class DreamboxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Dreambox config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return DreamboxOptionsFlowHandler(config_entry)

    def __init__(self):
        self._host = None
        self._name = None
        self._port = None
        self._username = DEFAULT_USERNAME
        self._password = DEFAULT_PASSWORD
        self._ssl = DEFAULT_SSL
        self._piconpath = DEFAULT_PICON_PATH
        self._api = None

    def _checkConnection(self):
        self._api = DreamboxApi(
            host=self._host,
            port=self._port,
            user=self._username,
            password=self._password,
            https=self._ssl,
            piconpath=self._piconpath,
        )
        try:
            self._api.get_deviceinfo()
        except AuthenticationFailed:
            return RESULT_INVALID_AUTH
        if not self._api.available:
            return RESULT_CANNOT_CONNECT
        return RESULT_SUCCESS

    def _getEntry(self):
        data = {
            CONF_HOST: self._host,
            CONF_NAME: self._name,
            CONF_PORT: self._port,
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_SSL: self._ssl,
            CONF_PATH: self._piconpath,
        }
        return self.async_create_entry(title=self._name, data=data)

    async def async_step_import(self, user_input=None):
        """Handle configuration by yaml file."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._name = user_input[CONF_NAME]
            self._host = user_input[CONF_HOST]
            self._port = user_input[CONF_PORT]
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._ssl = user_input[CONF_SSL]
            self._piconpath = user_input[CONF_PATH]

            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.data[CONF_HOST] == user_input[CONF_HOST]:
                    return self.async_abort(reason="already_configured")

            result = await self.hass.async_add_executor_job(self._checkConnection)
            if RESULT_SUCCESS:
                await self.async_set_unique_id(self._api.mac)
                self._abort_if_unique_id_configured({CONF_HOST: self._host})

                for progress in self._async_in_progress():
                    if progress.get("context", {}).get(CONF_HOST) == self._host:
                        return self.async_abort(reason="already_in_progress")

                # update old and user-configured config entries
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry.data[CONF_HOST] == self._host:
                        if self._api.mac and not entry.unique_id:
                            self.hass.config_entries.async_update_entry(
                                entry, unique_id=self._api.mac
                            )
                        return self.async_abort(reason="already_configured")

                return self._getEntry()
            else:
                errors["base"] = result
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA_USER,
        )

    async def async_step_ssdp(self, discovery_info):
        """Handle a flow initialized by ssdp discovery."""
        url = urlparse(discovery_info.upnp[ssdp.ATTR_UPNP_PRESENTATION_URL])
        self._host = url.hostname
        self._name = discovery_info.upnp.get(ssdp.ATTR_UPNP_MODEL_NAME)
        self._port = url.port or DEFAULT_PORT

        uuid = discovery_info.upnp.get(ssdp.ATTR_UPNP_UDN)
        if uuid:
            if uuid.startswith("uuid:"):
                uuid = uuid[5:]
        await self.async_set_unique_id(uuid)
        self._abort_if_unique_id_configured({CONF_HOST: self._host})
        for progress in self._async_in_progress():
            if progress.get("context", {}).get(CONF_HOST) == self._host:
                return self.async_abort(reason="already_in_progress")

        # update old and user-configured config entries
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data[CONF_HOST] == self._host:
                if uuid and not entry.unique_id:
                    self.hass.config_entries.async_update_entry(entry, unique_id=uuid)
                return self.async_abort(reason="already_configured")

        self.context.update({"title_placeholders": {"name": self._name}})
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Handle user-confirmation of discovered node."""
        errors = {}
        if user_input is not None:
            self._name = user_input[CONF_NAME]
            self._port = user_input[CONF_PORT]
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._ssl = user_input[CONF_SSL]
            self._piconpath = user_input[CONF_PATH]
            result = await self.hass.async_add_executor_job(self._checkConnection)
            if result == RESULT_SUCCESS:
                return self._getEntry()
            errors["base"] = result
        data = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=self._name): cv.string,
                vol.Optional(CONF_PORT, default=self._port): cv.port,
                vol.Optional(CONF_USERNAME, default=self._username): cv.string,
                vol.Optional(CONF_PASSWORD, default=self._password): cv.string,
                vol.Optional(CONF_SSL, default=self._ssl): cv.boolean,
                vol.Optional(CONF_PATH, default=self._piconpath): cv.string,
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=data,
            description_placeholders={"name": self._name},
            errors=errors,
        )


class DreamboxOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        return await self.async_step_dreambox(user_input)

    async def async_step_dreambox(self, user_input=None):
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)
        options = self.config_entry.options
        piconpath = options.get(CONF_PATH, DEFAULT_PICON_PATH)

        return self.async_show_form(
            step_id="dreambox",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PATH, default=piconpath): cv.string,
                }
            ),
        )

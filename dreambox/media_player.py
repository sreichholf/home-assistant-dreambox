"""Support for dreamboxes"""
from typing import Optional

from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaPlayerEntity,
)
from homeassistant.components.media_player.const import (
    MediaClass,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_player.errors import MediaPlayerException
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PATH,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)

SUPPORTED_DREAMBOX = (
    MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
)

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDeviceClass,
)
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    ATTR_MEDIA_DESCRIPTION,
    ATTR_MEDIA_END_TIME,
    ATTR_MEDIA_START_TIME,
    CONF_CONNECTIONS,
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_PICON_PATH,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_USERNAME,
    DOMAIN,
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
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


async def async_setup_entry(hass, config_entry, async_add_entities):
    device = hass.data[DOMAIN][CONF_CONNECTIONS][config_entry.entry_id]
    async_add_entities([DreamboxDevice(config_entry.data[CONF_NAME], device)], True)


class DreamboxDevice(MediaPlayerEntity):
    """Representation of an Enigma2 box."""

    def __init__(self, name, device):
        """Initialize the Enigma2 device."""
        self._name = name
        self._bouquet = None
        self._dreambox = device
        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER
        self._attr_device_info = DeviceInfo(
            name=name,
            manufacturer="Leontech Ltd.",
            model=f"Dreambox {device.deviceinfo.deviceName.rstrip()}",
            identifiers={(DOMAIN, device.mac)},
            connections={(CONNECTION_NETWORK_MAC, device.mac)},
            sw_version=device.deviceinfo.enigmaVersion,
        )
        self._attr_icon = "mdi:set-top-box"
        self._attr_name = name
        self._attr_supported_features = SUPPORTED_DREAMBOX
        self._attr_unique_id = device.mac
        self._attr_media_content_type = MediaType.TVSHOW

    def turn_off(self):
        """Turn off media player."""
        self._dreambox.standby = True

    def turn_on(self):
        """Turn the media player on."""
        self._dreambox.standby = False

    @property
    def media_image_url(self) -> Optional[str]:
        return self._dreambox.picon()

    def set_volume_level(self, volume) -> None:
        """Set volume level, range 0..1."""
        self._dreambox.volume = int(volume * 100)

    def volume_up(self) -> None:
        """Volume up the media player."""
        self._dreambox.volumeUp()

    def volume_down(self) -> None:
        """Volume down media player."""
        self._dreambox.volumeDown()

    def media_stop(self) -> None:
        """Send stop command."""
        self._dreambox.stop()

    def media_play_pause(self) -> None:
        self._dreambox.tooglePlayPause()

    def media_play(self) -> None:
        """Play media."""
        self._dreambox.tooglePlayPause()

    def media_pause(self) -> None:
        """Pause the media player."""
        self._dreambox.tooglePlayPause()

    def media_next_track(self) -> None:
        """Send next track command."""
        self._dreambox.set_channel_up()

    def media_previous_track(self) -> None:
        """Send next track command."""
        self._dreambox.set_channel_down()

    def mute_volume(self, mute) -> None:
        """Mute or unmute."""
        self._dreambox.muted = mute

    def _browse_media_library(
        self, media_content_type, media_content_id
    ) -> "BrowseMedia":
        self._bouquet = None
        library_info = {
            "title": "Favorites",
            "media_class": MediaClass.DIRECTORY,
            "children_media_class": MediaClass.PLAYLIST,
            "media_content_id": "library",
            "media_content_type": "library",
            "can_play": False,
            "can_expand": True,
            "children": [],
        }

        for bouquet in self._dreambox.bouquets:
            bouquet_info = {
                "title": bouquet.name,
                "media_class": MediaClass.PLAYLIST,
                "children_media_class": MediaClass.CHANNEL,
                "media_content_id": bouquet.ref,
                "media_content_type": "bouquet",
                "can_play": False,
                "can_expand": True,
                "children": [],
            }
            library_info["children"].append(BrowseMedia(**bouquet_info))
        return BrowseMedia(**library_info)

    def _browse_media_bouquet(
        self, media_content_type, media_content_id
    ) -> "BrowseMedia":
        bouquet = None
        for b in self._dreambox.bouquets:
            if b.ref == media_content_id:
                bouquet = b
        if not bouquet:
            return None
        self._bouquet = bouquet
        bouquet_info = {
            "title": bouquet.name,
            "media_class": MediaClass.PLAYLIST,
            "children_media_class": MediaClass.VIDEO,
            "media_content_id": bouquet.ref,
            "media_content_type": "bouquet",
            "can_play": False,
            "can_expand": True,
            "children": [],
        }
        for service in bouquet.services:
            service_info = {
                "title": service.name,
                "media_class": MediaClass.VIDEO,
                "media_content_id": service.ref,
                "media_content_type": MediaType.TVSHOW,
                "can_play": True,
                "thumbnail": self._dreambox.picon(service),
                "can_expand": False,
            }
            bouquet_info["children"].append(BrowseMedia(**service_info))
        response = BrowseMedia(**bouquet_info)
        return response

    async def async_browse_media(
        self, media_content_type: Optional[str], media_content_id: Optional[str]
    ) -> "BrowseMedia":
        builder = None
        if media_content_type in [None, "library"]:
            builder = self._browse_media_library
        elif media_content_type == "bouquet":
            builder = self._browse_media_bouquet
        response = None
        if builder:
            response = await self.hass.async_add_executor_job(
                builder, media_content_type, media_content_id
            )
        if response is None:
            raise BrowseError(
                f"Media not found: {media_content_type} / {media_content_id}"
            )
        return response

    def play_media(self, media_type: str, media_id: str, **kwargs) -> None:
        if media_type != MediaType.TVSHOW or not self._bouquet:
            raise MediaPlayerException(
                f"Media not supported: {media_type} / {media_id}"
            )
        for service in self._bouquet.services:
            if service.ref == media_id:
                self._dreambox.playService(service, self._bouquet)
                return
        raise MediaPlayerException(f"Channel not found: {media_type} / {media_id}")

    def update(self) -> None:
        """Update state of the media_player."""
        self._dreambox.update()

        if self._dreambox.standby:
            self._attr_state = MediaPlayerState.OFF
        elif self._dreambox.current:
            self._attr_state = MediaPlayerState.PLAYING
        else:
            self._attr_state = MediaPlayerState.ON

        self._attr_available = self._dreambox.available
        self._attr_media_title = self._dreambox.current.name
        self._attr_media_series_title = self._dreambox.current.now.title
        self._attr_media_channel = self._dreambox.current.name
        self._attr_media_content_id = self._dreambox.current.ref
        self._attr_media_duration = self._dreambox.current.now.duration or None
        self._attr_is_volume_muted = self._dreambox.muted
        self._attr_volume_level = float(self._dreambox.volume) / 100.0

        if self._dreambox.bouquet:
            self._attr_media_playlist = self._dreambox.bouquet.name
        else:
            self._attr_media_playlist = None

        if self._attr_state == MediaPlayerState.PLAYING:
            self._attr_extra_state_attributes = {
                ATTR_MEDIA_DESCRIPTION: self._dreambox.current.now.title,
                ATTR_MEDIA_START_TIME: self._dreambox.current.now.start,
                ATTR_MEDIA_END_TIME: self._dreambox.current.now.end,
            }
        else:
            self._attr_extra_state_attributes = {}

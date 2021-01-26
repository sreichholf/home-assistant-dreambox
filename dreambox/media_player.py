"""Support for dreamboxes"""
from dreamboxapi.api import DreamboxApi
from typing import Dict, List, Any, Optional

from homeassistant.components.media_player.errors import MediaPlayerException

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    BrowseMedia,
    BrowseError,
)
from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_CHANNEL,
    MEDIA_CLASS_PLAYLIST,
    MEDIA_CLASS_VIDEO,
    MEDIA_TYPE_TVSHOW,
    SUPPORT_BROWSE_MEDIA,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_STOP,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PATH,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
)


SUPPORTED_DREAMBOX = (
    SUPPORT_BROWSE_MEDIA
    | SUPPORT_PAUSE
    | SUPPORT_PLAY
    | SUPPORT_PLAY_MEDIA
    | SUPPORT_STOP
    | SUPPORT_TURN_OFF
    | SUPPORT_TURN_ON
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_VOLUME_STEP
)

from .const import (
    DOMAIN,
    CONF_CONNECTIONS,
    ATTR_MEDIA_DESCRIPTION,
    ATTR_MEDIA_END_TIME,
    ATTR_MEDIA_START_TIME,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_PICON_PATH,
)


import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.media_player import PLATFORM_SCHEMA

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

    @property
    def unique_id(self):
        return self._dreambox.mac

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._dreambox.mac)},
            "name": self._name,
            "manufacturer": "Leontech Ltd.",
            "model": f"Dreambox {self._dreambox.deviceinfo.deviceName}".rstrip(),
            "sw_version": self._dreambox.deviceinfo.enigmaVersion,
        }

    @property
    def icon(self) -> str:
        """Return the icon of the device."""
        return "mdi:set-top-box"

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the device."""
        if self._dreambox.standby:
            return STATE_OFF
        return STATE_PLAYING if self._dreambox.current else STATE_ON

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return self._dreambox.available

    @property
    def supported_features(self) -> int:
        """Flag of media commands that are supported."""
        return SUPPORTED_DREAMBOX

    def turn_off(self):
        """Turn off media player."""
        self._dreambox.standby = True

    def turn_on(self):
        """Turn the media player on."""
        self._dreambox.standby = False

    @property
    def media_title(self) -> Optional[str]:
        """Title of current playing media."""
        return self._dreambox.current.name

    @property
    def media_series_title(self) -> Optional[str]:
        """Return the title of current episode of TV show."""
        return self._dreambox.current.now.title

    @property
    def media_channel(self) -> Optional[str]:
        """Channel of current playing media."""
        return self._dreambox.current.name

    @property
    def media_content_id(self) -> Optional[str]:
        """Service Ref of current playing media."""
        return self._dreambox.current.ref

    @property
    def media_content_type(self) -> str:
        """Type of video currently playing."""
        return MEDIA_TYPE_TVSHOW

    @property
    def media_duration(self) -> Optional[int]:
        return self._dreambox.current.now.duration or None

    @property
    def is_volume_muted(self) -> bool:
        """Boolean if volume is currently muted."""
        return self._dreambox.muted

    @property
    def media_playlist(self) -> Optional[str]:
        if self._dreambox.bouquet:
            return self._dreambox.bouquet.name

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

    @property
    def volume_level(self) -> float:
        """Volume level of the media player (0..1)."""
        return float(self._dreambox.volume) / 100.0

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
            "media_class": MEDIA_CLASS_DIRECTORY,
            "children_media_class": MEDIA_CLASS_PLAYLIST,
            "media_content_id": "library",
            "media_content_type": "library",
            "can_play": False,
            "can_expand": True,
            "children": [],
        }

        for bouquet in self._dreambox.bouquets:
            bouquet_info = {
                "title": bouquet.name,
                "media_class": MEDIA_CLASS_PLAYLIST,
                "children_media_class": MEDIA_CLASS_CHANNEL,
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
            "media_class": MEDIA_CLASS_PLAYLIST,
            "children_media_class": MEDIA_CLASS_VIDEO,
            "media_content_id": bouquet.ref,
            "media_content_type": "bouquet",
            "can_play": False,
            "can_expand": True,
            "children": [],
        }
        for service in bouquet.services:
            service_info = {
                "title": service.name,
                "media_class": MEDIA_CLASS_VIDEO,
                "media_content_id": service.ref,
                "media_content_type": MEDIA_TYPE_TVSHOW,
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
        if media_type != MEDIA_TYPE_TVSHOW or not self._bouquet:
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

    @property
    def device_state_attributes(self) -> Dict[str, str]:
        """Return device specific state attributes.

        current.now.title: Current program event title.
        current.now.start:  is in the format '21:00'.
        current.now.end:    is in the format '21:00'.
        """
        if self._dreambox.standby or not self._dreambox.current:
            return {}
        return {
            ATTR_MEDIA_DESCRIPTION: self._dreambox.current.now.title,
            ATTR_MEDIA_START_TIME: self._dreambox.current.now.start,
            ATTR_MEDIA_END_TIME: self._dreambox.current.now.end,
        }

"""Support for Dreamboxes."""

from collections.abc import Callable
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from dreamboxapi.data import ServiceList
from dreamboxapi.exceptions import DreamboxError
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    BrowseError,
    BrowseMedia,
    MediaPlayerDeviceClass,
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
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_MEDIA_DESCRIPTION,
    ATTR_MEDIA_END_TIME,
    ATTR_MEDIA_START_TIME,
    CONF_PLAY_PAUSE_TOGGLE,
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_PICON_PATH,
    DEFAULT_PLAY_PAUSE_TOGGLE,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_USERNAME,
)
from .coordinator import DreamboxConfigEntry, DreamboxCoordinator

PARALLEL_UPDATES = 1

SUPPORTED_DREAMBOX = (
    MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
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


async def async_setup_entry(
    hass, config_entry: DreamboxConfigEntry, async_add_entities
) -> None:
    """Set up the Dreambox media player."""
    async_add_entities([DreamboxDevice(config_entry.runtime_data, config_entry)])


class DreamboxDevice(CoordinatorEntity[DreamboxCoordinator], MediaPlayerEntity):
    """Representation of an Enigma2 box."""

    def __init__(
        self, coordinator: DreamboxCoordinator, config_entry: DreamboxConfigEntry
    ) -> None:
        """Initialize the Enigma2 device."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_assumed_state = True
        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER
        self._attr_device_info = coordinator.device_info
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:set-top-box"
        self._attr_media_content_type = MediaType.TVSHOW
        self._attr_name = None
        self._attr_supported_features = SUPPORTED_DREAMBOX
        self._attr_unique_id = coordinator.unique_id
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Copy the coordinator snapshot onto the media player attributes."""
        data = self.coordinator.data
        if data is None:
            return

        current = data.current
        now = current.now if current is not None else None

        if data.in_standby:
            state = MediaPlayerState.OFF
        elif current is not None:
            state = MediaPlayerState.PLAYING
        else:
            state = MediaPlayerState.ON

        self._attr_state = state
        self._attr_assumed_state = state != MediaPlayerState.OFF
        self._attr_is_volume_muted = data.muted
        self._attr_volume_level = data.volume / 100.0
        self._attr_media_image_url = (
            self.coordinator.api.picon(current) if current is not None else None
        )
        self._attr_media_title = current.name if current is not None else None
        self._attr_media_series_title = now.title if now is not None else None
        self._attr_media_channel = current.name if current is not None else None
        self._attr_media_content_id = current.ref if current is not None else None
        self._attr_media_duration = (now.duration or None) if now is not None else None
        bouquet = self.coordinator.api.bouquet
        self._attr_media_playlist = bouquet.name if bouquet is not None else None

        if state == MediaPlayerState.PLAYING and now is not None:
            self._attr_extra_state_attributes = {
                ATTR_MEDIA_DESCRIPTION: now.title,
                ATTR_MEDIA_START_TIME: now.start,
                ATTR_MEDIA_END_TIME: now.end,
            }
        else:
            self._attr_extra_state_attributes = {}

    async def async_turn_off(self) -> None:
        """Turn off media player."""
        await self._async_command(self._set_standby, True)

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self._async_command(self._set_standby, False)

    def _set_standby(self, standby: bool) -> None:
        self.coordinator.api.standby = standby

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self._async_command(self._set_volume, volume)

    def _set_volume(self, volume: float) -> None:
        self.coordinator.api.volume = int(volume * 100)

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        await self._async_command(self.coordinator.api.volumeUp)

    async def async_volume_down(self) -> None:
        """Volume down media player."""
        await self._async_command(self.coordinator.api.volumeDown)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute."""
        await self._async_command(self._set_muted, mute)

    def _set_muted(self, muted: bool) -> None:
        self.coordinator.api.muted = muted

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._async_remote(self.coordinator.api.stop)

    @property
    def _play_pause_toggle(self) -> bool:
        return self._config_entry.options.get(
            CONF_PLAY_PAUSE_TOGGLE, DEFAULT_PLAY_PAUSE_TOGGLE
        )

    async def async_media_play_pause(self) -> None:
        """Send play/pause toggle command."""
        await self._async_remote(self.coordinator.api.togglePlayPause)

    async def async_media_play(self) -> None:
        """Play media."""
        if self._play_pause_toggle:
            await self._async_remote(self.coordinator.api.togglePlayPause)
        else:
            await self._async_remote(self.coordinator.api.play)

    async def async_media_pause(self) -> None:
        """Pause the media player."""
        if self._play_pause_toggle:
            await self._async_remote(self.coordinator.api.togglePlayPause)
        else:
            await self._async_remote(self.coordinator.api.pause)

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self._async_remote(self.coordinator.api.set_channel_up)

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self._async_remote(self.coordinator.api.set_channel_down)

    async def _async_command(self, target: Callable[..., Any], *args: Any) -> None:
        """Run a command in the executor and refresh the coordinator."""
        try:
            await self.hass.async_add_executor_job(target, *args)
        except DreamboxError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    def _check_remote(self, result: Any) -> None:
        if not result or not getattr(result, "state", False):
            raise MediaPlayerException("Failed to send remote control command")

    async def _async_remote(self, target: Callable[[], Any]) -> None:
        """Run a remote-control command and refresh the coordinator."""
        try:
            result = await self.hass.async_add_executor_job(target)
        except DreamboxError as err:
            raise HomeAssistantError(str(err)) from err
        self._check_remote(result)
        await self.coordinator.async_request_refresh()

    async def _async_bouquets(self) -> list[ServiceList]:
        try:
            return await self.coordinator.async_get_bouquets()
        except HomeAssistantError as err:
            raise BrowseError(str(err)) from err

    def _browse_media_library(self, bouquets: list[ServiceList]) -> BrowseMedia:
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

        for bouquet in bouquets:
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
        self, bouquets: list[ServiceList], media_content_id: str | None
    ) -> BrowseMedia | None:
        bouquet = None
        for candidate in bouquets:
            if candidate.ref == media_content_id:
                bouquet = candidate
                break
        if bouquet is None:
            return None

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
                "thumbnail": self.get_browse_image_url(MediaType.TVSHOW, service.ref),
                "can_expand": False,
            }
            bouquet_info["children"].append(BrowseMedia(**service_info))
        return BrowseMedia(**bouquet_info)

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Return the current channel icon with webinterface authentication."""
        current = self.coordinator.data.current
        if current is None:
            return (None, None)
        try:
            return await self.hass.async_add_executor_job(
                self.coordinator.api.get_picon, current
            )
        except DreamboxError:
            return (None, None)

    async def async_get_browse_image(
        self,
        media_content_type: str,
        media_content_id: str,
        media_image_id: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """Return a browse thumbnail with webinterface authentication."""
        found = self.coordinator.find_service(media_content_id)
        if found is None:
            return (None, None)
        service, _bouquet = found
        try:
            return await self.hass.async_add_executor_job(
                self.coordinator.api.get_picon, service
            )
        except DreamboxError:
            return (None, None)

    async def async_browse_media(
        self, media_content_type: str | None, media_content_id: str | None
    ) -> BrowseMedia:
        """Browse the Dreambox bouquets and their services."""
        if media_content_type in (None, "library"):
            return self._browse_media_library(await self._async_bouquets())
        if media_content_type == "bouquet":
            response = self._browse_media_bouquet(
                await self._async_bouquets(), media_content_id
            )
            if response is not None:
                return response
        raise BrowseError(f"Media not found: {media_content_type} / {media_content_id}")

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a channel from the browsed bouquets."""
        if media_type != MediaType.TVSHOW:
            raise MediaPlayerException(
                f"Media not supported: {media_type} / {media_id}"
            )
        try:
            await self.coordinator.async_play_service(media_id)
        except HomeAssistantError as err:
            raise MediaPlayerException(str(err)) from err
        await self.coordinator.async_request_refresh()

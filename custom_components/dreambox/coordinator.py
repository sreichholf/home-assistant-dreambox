"""Coordinator and shared data for the Dreambox integration."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

from dreamboxapi.api import AuthenticationFailed, DreamboxApi
from dreamboxapi.data import Service, ServiceList
from dreamboxapi.exceptions import DreamboxError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)
BOUQUET_CACHE_TTL = timedelta(hours=1)
MAC_ADDRESS = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

type DreamboxConfigEntry = ConfigEntry[DreamboxCoordinator]


@dataclass(frozen=True)
class DreamboxData:
    """State polled from the Dreambox."""

    current: Service | None
    in_standby: bool
    volume: int
    muted: bool | None


class DreamboxCoordinator(DataUpdateCoordinator[DreamboxData]):
    """Poll a Dreambox and share its API client with the platforms."""

    config_entry: DreamboxConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: DreamboxConfigEntry,
        api: DreamboxApi,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} {config_entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self._device_info: DeviceInfo | None = None
        self._bouquets: list[ServiceList] | None = None
        self._bouquets_updated: float | None = None
        self._bouquet_lock = asyncio.Lock()
        self._bouquet_refresh_task: asyncio.Task[None] | None = None

    @property
    def unique_id(self) -> str:
        """Return the stable identifier for this Dreambox."""
        return self.api.mac or self.config_entry.unique_id or self.config_entry.entry_id

    def _normalized_mac(self) -> str:
        """Return the normalized MAC address, if the box reports a valid one."""
        mac = self.api.mac
        if not mac or not MAC_ADDRESS.match(mac):
            return ""
        normalized = format_mac(mac)
        if normalized == "00:00:00:00:00:00":
            return ""
        return normalized

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device registry information for this Dreambox."""
        return self._device_info

    async def _async_setup(self) -> None:
        """Fetch the device information once during setup."""
        try:
            await self.hass.async_add_executor_job(self.api.get_deviceinfo)
        except AuthenticationFailed as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except DreamboxError as err:
            raise ConfigEntryNotReady(str(err)) from err

        if self.api.deviceinfo is None:
            raise ConfigEntryNotReady("Failed to obtain device information")

        self._device_info = self._build_device_info()

    def _build_device_info(self) -> DeviceInfo:
        """Build the canonical device registry entry."""
        device = self.api.deviceinfo
        if device is None:
            raise ConfigEntryNotReady("Failed to obtain device information")

        unique_id = self.unique_id
        if not unique_id:
            raise ConfigEntryNotReady("Failed to determine the device identifier")

        config_entry = self.config_entry
        mac = self._normalized_mac()
        scheme = "https" if config_entry.data[CONF_SSL] else "http"
        model = device.deviceName.rstrip() or DEFAULT_NAME
        return DeviceInfo(
            configuration_url=(
                f"{scheme}://{config_entry.data[CONF_HOST]}"
                f":{config_entry.data[CONF_PORT]}/"
            ),
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            identifiers={(DOMAIN, unique_id)},
            manufacturer="Dream Property",
            model=f"Dreambox {model}",
            name=config_entry.data.get(CONF_NAME, config_entry.title or DEFAULT_NAME),
            sw_version=device.enigmaVersion,
        )

    async def _async_update_data(self) -> DreamboxData:
        """Poll the current service and power state in one executor job."""
        try:
            await self.hass.async_add_executor_job(self.api.update_status)
        except AuthenticationFailed as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except DreamboxError as err:
            raise UpdateFailed(str(err)) from err

        return DreamboxData(
            current=self.api.current,
            in_standby=self.api.standby,
            volume=self.api.volume,
            muted=self.api.muted,
        )

    async def async_get_bouquets(self, force: bool = False) -> list[ServiceList]:
        """Return the bouquets, loading them lazily.

        A stale cache is served immediately while a refresh runs in the
        background, so browsing never waits for the bouquet request.
        """
        if not force and self._bouquets is not None:
            if self._bouquets_are_stale():
                self._async_schedule_bouquet_refresh()
            return list(self._bouquets)
        return await self._async_refresh_bouquets(force=force)

    def find_service(self, ref: str) -> tuple[Service, ServiceList] | None:
        """Return a service and its bouquet from the cached bouquet list."""
        for bouquet in self._bouquets or []:
            for service in bouquet.services:
                if service.ref == ref:
                    return service, bouquet
        return None

    async def async_play_service(self, ref: str) -> None:
        """Zap to a service, refreshing the bouquets once when it is unknown."""
        found = self.find_service(ref)
        if found is None:
            await self.async_get_bouquets(force=True)
            found = self.find_service(ref)
        if found is None:
            raise HomeAssistantError(f"Channel not found: {ref}")

        service, bouquet = found
        try:
            result = await self.hass.async_add_executor_job(
                self.api.playService, service, bouquet
            )
        except DreamboxError as err:
            raise HomeAssistantError(f"Failed to switch channel: {err}") from err

        if result is None or not result.state:
            raise HomeAssistantError(f"Failed to switch channel: {ref}")

    def _bouquets_are_stale(self) -> bool:
        """Return whether the cached bouquets are missing or expired."""
        if self._bouquets is None or self._bouquets_updated is None:
            return True
        return monotonic() - self._bouquets_updated > BOUQUET_CACHE_TTL.total_seconds()

    async def _async_refresh_bouquets(self, force: bool = False) -> list[ServiceList]:
        """Load the bouquets, sharing one request between concurrent callers."""
        async with self._bouquet_lock:
            if (
                not force
                and self._bouquets is not None
                and not self._bouquets_are_stale()
            ):
                return list(self._bouquets)

            try:
                await self.hass.async_add_executor_job(self.api.get_bouquets)
            except DreamboxError as err:
                raise HomeAssistantError(
                    f"Failed to fetch bouquets from the Dreambox: {err}"
                ) from err

            bouquets = list(self.api.bouquets)
            if bouquets or self._bouquets is None:
                self._bouquets = bouquets
                self._bouquets_updated = monotonic()
            return list(self._bouquets)

    @callback
    def _async_schedule_bouquet_refresh(self) -> None:
        """Refresh stale bouquets in the background, once at a time."""
        if (
            self._bouquet_refresh_task is not None
            and not self._bouquet_refresh_task.done()
        ):
            return

        self._bouquet_refresh_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_background_refresh_bouquets(),
            "dreambox bouquet refresh",
        )

    async def _async_background_refresh_bouquets(self) -> None:
        """Refresh stale bouquets without failing the browse request."""
        try:
            await self._async_refresh_bouquets()
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to refresh the bouquet list: %s", err)
        finally:
            self._bouquet_refresh_task = None

    async def async_shutdown(self) -> None:
        """Cancel background work and close the API session."""
        if (
            self._bouquet_refresh_task is not None
            and not self._bouquet_refresh_task.done()
        ):
            self._bouquet_refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._bouquet_refresh_task
        await self.hass.async_add_executor_job(self.api.close)

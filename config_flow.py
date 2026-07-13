"""Config flow for Tuya Local BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .devices import get_device_readable_name
from .keyman import HASSTuyaBLEDeviceManager
from .tuya_ble import SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


class TuyaBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._data: dict[str, Any] = {}
        self._manager: HASSTuyaBLEDeviceManager | None = None
        self._get_device_info_error = False

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manual setup simply scans for BLE devices."""
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)

        return await self.async_step_device(user_input)

    async def async_step_bluetooth(
        self,
        discovery_info: BluetoothServiceInfoBleak,
    ) -> ConfigFlowResult:
        """Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info

        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)

        self.context["title_placeholders"] = {
            "name": await get_device_readable_name(
                discovery_info,
                self._manager,
            )
        }

        return await self.async_step_device()

    async def async_step_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose discovered device."""

        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]

            local_name = await get_device_readable_name(
                discovery_info,
                self._manager,
            )

            await self.async_set_unique_id(
                discovery_info.address,
                raise_on_progress=False,
            )

            self._abort_if_unique_id_configured()

            credentials = await self._manager.get_device_credentials(
                discovery_info.address,
                self._get_device_info_error,
                True,
            )

            self._data[CONF_ADDRESS] = discovery_info.address

            if credentials is None:
                self._get_device_info_error = True
                errors["base"] = "device_not_registered"
            else:
                return self.async_create_entry(
                    title=local_name,
                    data={CONF_ADDRESS: discovery_info.address},
                    options=self._data,
                )

        if self._discovery_info:
            self._discovered_devices[self._discovery_info.address] = (
                self._discovery_info
            )
        else:
            current_addresses = self._async_current_ids()

            for discovery in async_discovered_service_info(self.hass):
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                    or discovery.service_data is None
                    or SERVICE_UUID not in discovery.service_data
                ):
                    continue

                self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="no_unconfigured_devices")

        default_address = (
            user_input.get(CONF_ADDRESS)
            if user_input
            else next(iter(self._discovered_devices))
        )

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADDRESS,
                        default=default_address,
                    ): vol.In(
                        {
                            info.address: await get_device_readable_name(
                                info,
                                self._manager,
                            )
                            for info in self._discovered_devices.values()
                        }
                    )
                }
            ),
            errors=errors,
        )

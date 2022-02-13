# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 Luis López <luis@cuarentaydos.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.


from typing import Any, Optional

import ideenergy
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from . import _LOGGER
from .const import (
    CONF_CONTRACT,
    CONF_ENABLE_DIRECT_MEASURE,
    DEFAULT_NAME,
    DOMAIN,
)

AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_USERNAME, default="ldotlopez@gmail.com"): str,
        vol.Required(CONF_PASSWORD, default="hAQiunh9XgKdctxa"): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    VERSION = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.info = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()

            try:
                info = await validate_user_input(self.hass, user_input)

            except ideenergy.ClientError:
                errors["base"] = "invalid_auth"

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            else:
                self.info = info
                self.info[CONF_NAME] = user_input.get(CONF_NAME, DEFAULT_NAME)

                return await self.async_step_contract()
                # info[CONF_NAME] = user_input.get(CONF_NAME, DEFAULT_NAME)
                # return self.async_create_entry(title=info[CONF_NAME], data=info)

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    async def async_step_contract(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        contracts = await self.info["api"].get_contracts()
        contracts = {x["direccion"]: x["codContrato"] for x in contracts}

        schema = vol.Schema({vol.Required(CONF_CONTRACT): vol.In(contracts.keys())})

        if not user_input:
            return self.async_show_form(step_id="contract", data_schema=schema)

        self.info[CONF_CONTRACT] = contracts[user_input["contract"]]
        self.info[CONF_NAME] = self.info[CONF_NAME] + "_" + self.info[CONF_CONTRACT]

        return self.async_create_entry(title=self.info[CONF_NAME], data=self.info)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        OPTIONS_SCHEMA = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_DIRECT_MEASURE,
                    default=self.config_entry.options.get(CONF_ENABLE_DIRECT_MEASURE),
                ): bool
            }
        )

        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)


async def validate_user_input(hass, user_input):
    username = user_input[CONF_USERNAME]
    password = user_input[CONF_PASSWORD]

    sess = async_create_clientsession(hass)
    client = ideenergy.Client(sess, username, password)

    await client.login()
    return {
        "api": client,
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
    }

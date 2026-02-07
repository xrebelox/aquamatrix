from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_TENANT, CONF_USERNAME, CONF_PASSWORD
from .api import SMSNetClient
class SMSNetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            tenant = user_input[CONF_TENANT].strip("/"); username = user_input[CONF_USERNAME]; password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass); client = SMSNetClient(session, "https://www.aquamatrix.pt", tenant, username, password, None)
            try: await client.login_basic()
            except Exception: errors["base"] = "auth"
            else:
                await self.async_set_unique_id(f"{tenant}:{username}"); self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"SMSnet ({tenant})", data=user_input)
        schema = vol.Schema({vol.Required(CONF_TENANT, default="SMSnet"): str, vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
    async def async_step_import(self, import_data) -> FlowResult:
        tenant = import_data.get(CONF_TENANT, "SMSnet").strip("/")
        username = import_data.get(CONF_USERNAME, "")
        password = import_data.get(CONF_PASSWORD, "")
        await self.async_set_unique_id(f"{tenant}:{username}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"SMSnet ({tenant})", data={CONF_TENANT: tenant, CONF_USERNAME: username, CONF_PASSWORD: password})

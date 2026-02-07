from __future__ import annotations
import logging
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, PLATFORMS, DEFAULT_BASE_URL, CONF_TENANT, CONF_USERNAME, CONF_PASSWORD
from .coordinator import SMSNetCoordinator
from .api import SMSNetClient

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if DOMAIN in config:
        data = config[DOMAIN]
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={
                    CONF_TENANT: data.get(CONF_TENANT, "SMSnet"),
                    CONF_USERNAME: data.get(CONF_USERNAME, ""),
                    CONF_PASSWORD: data.get(CONF_PASSWORD, ""),
                },
            )
        )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    tenant = entry.data[CONF_TENANT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    base_url = DEFAULT_BASE_URL

    client = SMSNetClient(session, base_url, tenant, username, password, _LOGGER)
    coordinator = SMSNetCoordinator(hass, client, logger=_LOGGER)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok

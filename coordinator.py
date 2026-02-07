from __future__ import annotations
import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import SMSNetClient
UPDATE_INTERVAL = timedelta(hours=6)
class SMSNetCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: SMSNetClient, logger: logging.Logger | None = None) -> None:
        super().__init__(hass, logger=logger or logging.getLogger(__name__), name="SMSnet Coordinator", update_interval=UPDATE_INTERVAL)
        self.client = client
    async def _async_update_data(self):
        results = {}; errors = []
        try:
            if not getattr(self.client, "_rvt", None):
                await self.client.login()
        except Exception as e:
            errors.append(f"login: {e}")
        async def get_safe(key, coro):
            try: results[key] = await coro
            except Exception as e: errors.append(f"{key}: {e}")
        await get_safe("last_reading", self.client.get_last_reading())
        await get_safe("consumptions", self.client.get_consumptions_graph())
        await get_safe("billed", self.client.get_billed_graph())
        await get_safe("billing_info", self.client.get_billing_info())
        if results:
            self.logger.debug("SMSNET update ok keys=%s errors=%s", list(results.keys()), errors)
            return results
        raise UpdateFailed("; ".join(errors) if errors else "No data")

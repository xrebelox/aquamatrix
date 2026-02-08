from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
import datetime
import re
import logging

Logger = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    tenant = entry.data["tenant"]

    entities = [
        # Compatível com Energy (contador cumulativo)
        SMSnetSensor(
            coordinator, entry, tenant, "last_reading_value", "Água - Última leitura (m³)",
            unit="m³", device_class=SensorDeviceClass.WATER, state_class=SensorStateClass.TOTAL_INCREASING
        ),
        SMSnetSensor(coordinator, entry, tenant, "last_reading_date", "Água - Data última leitura", unit=None, device_class="date"),

        # Consumos mensais (medição)
        SMSnetSensor(
            coordinator, entry, tenant, "consumption_current_month", "Água - Consumo mês atual (m³)",
            unit="m³", device_class=SensorDeviceClass.WATER, state_class=SensorStateClass.TOTAL
        ),
        SMSnetSensor(
            coordinator, entry, tenant, "consumption_previous_month", "Água - Consumo mês anterior (m³)",
            unit="m³", device_class=SensorDeviceClass.WATER, state_class=SensorStateClass.TOTAL
        ),
        SMSnetSensor(coordinator, entry, tenant, "consumption_current_month_label", "Água - Consumo mês atual (label)", unit=None),

        # Faturação / dívida
        SMSnetSensor(
            coordinator, entry, tenant, "billed_last_value", "Água - Último valor faturado (€)",
            unit="€", state_class=SensorStateClass.MEASUREMENT
        ),
        SMSnetSensor(coordinator, entry, tenant, "billed_last_label", "Água - Fatura último mês (label)", unit=None),
        SMSnetSensor(
            coordinator, entry, tenant, "debt_total", "Água - Valor em dívida (€)",
            unit="€", state_class=SensorStateClass.MEASUREMENT
        ),
        SMSnetSensor(coordinator, entry, tenant, "next_due_date", "Água - Próxima data limite", unit=None, device_class="date"),
    ]
    async_add_entities(entities)

class SMSnetSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False
    def __init__(self, coordinator, entry, tenant: str, key: str, name: str, unit: str | None,
                 device_class: SensorDeviceClass | str | None = None,
                 state_class: SensorStateClass | None = None) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        if device_class: self._attr_device_class = device_class
        if state_class: self._attr_state_class = state_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Portal AQUAmatrix",
            "manufacturer": "Quinzico",
            "model": "SMSnet",
        }
    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        last = data.get("last_reading") or {}
        cons = data.get("consumptions") or {}
        billed = data.get("billed") or {}
        billinfo = data.get("billing_info") or {}
        if self._key == "last_reading_value":
            v = last.get("Value") or last.get("LastReadingValue") or "0"

            try:
                parsed_str = re.sub(r'\s', '', str(v)).replace(',', ".")
                return float(parsed_str)
            except Exception:
                Logger.error(f"Error parsing last reading value: {v}")
                return None
        if self._key == "last_reading_date":
            v = last.get("LastReadingDate") or last.get("Date")
            try: 
                return datetime.strptime(v, "%Y-%m-%d").date()
            except Exception: 
                Logger.error(f"Error parsing last reading date: {v}")
                return None
        if self._key in ("consumption_current_month", "consumption_previous_month", "consumption_current_month_label"):
            arr = []
            if isinstance(cons, dict) and "Values" in cons: arr = cons.get("Values") or []
            elif isinstance(cons, list): arr = cons
            if not arr: return None
            idx = -1 if self._key != "consumption_previous_month" else -2
            try: item = arr[idx]
            except Exception: return None
            if self._key == "consumption_current_month_label": return item.get("Label", "")
            val = item.get("FirstValue", item.get("Value", 0))
            try: return float(str(val).replace(",", "."))
            except Exception: return None
        if self._key in ("billed_last_value", "billed_last_label"):
            if not isinstance(billed, list) or not billed: return None
            last_item = billed[-1]
            if self._key == "billed_last_label": return last_item.get("Label", "")
            val = last_item.get("Value", 0)
            try: return float(str(val).replace(",", "."))
            except Exception: return None
        if self._key == "debt_total":
            for k in ("totalDebt", "valorEmDivida", "debt", "TotalDebt", "ValorEmDivida"):
                if k in billinfo:
                    try: return float(str(billinfo[k]).replace(",", "."))
                    except Exception: return None
            inv = billinfo.get("nextInvoice") or billinfo.get("proximaFatura") or {}
            for k in ("debt", "valor", "amount"):
                if k in inv:
                    try: return float(str(inv[k]).replace(",", "."))
                    except Exception: return None
            return None
        if self._key == "next_due_date":
            inv = billinfo.get("nextInvoice") or billinfo.get("proximaFatura") or {}
            v = inv.get("limitDate") or inv.get("dataLimite") or billinfo.get("limitDate") or billinfo.get("dataLimite")
            try: return datetime.strptime(v, "%Y-%m-%d").date()
            except Exception: return None
        return None

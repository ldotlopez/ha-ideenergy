"""Platform for sensor integration."""
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import STATE_CLASS_MEASUREMENT
from homeassistant.const import DEVICE_CLASS_ENERGY
from .const import DOMAIN
import random


# from homeassistant.components.sensor import (
#     STATE_CLASS_MEASUREMENT,
#     STATE_CLASS_TOTAL_INCREASING,
# )
# from homeassistant.const import (
#     DEVICE_CLASS_CURRENT,
#     DEVICE_CLASS_ENERGY,
#     DEVICE_CLASS_GAS,
#     DEVICE_CLASS_POWER,
#     DEVICE_CLASS_VOLTAGE,
# )

# def setup_platform(hass, config, add_entities, discovery_info=None):
#     """Set up the sensor platform."""
#     print(f"{__name__} {entry!r}")
#     add_entities([IDEEnergySensor()])


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    sensors = [
        IDEEnergyAccumulateSensor(hass.data[DOMAIN][config_entry.entry_id], name='consumed', key='accumulate')
    ]

    async_add_entities(sensors, True)  # Update entity on add


class IDEEnergyAccumulateSensor(Entity):
    """Representation of a Sensor."""

    # device_class: energy
    # icon: mdi:transmission-tower
    # state_class: measurement
    # unit_of_measurement: kWh

    def __init__(self, api, name, key):
        """Initialize the sensor."""
        self._state = None
        self._api = api

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'IDEEnergy consumed energy'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return ENERGY_KILO_WATT_HOUR

    @property
    def state_class(self):
        return STATE_CLASS_MEASUREMENT

    @property
    def device_class(self):
        return DEVICE_CLASS_ENERGY

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        print("Updating!")
        self._state = (self._state or 0) + random.randrange(0, 3)

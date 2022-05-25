# home-assistant ideenergy

[![hassfest validation](https://github.com/ldotlopez/ha-ideenergy/workflows/Validate%20with%20hassfest/badge.svg)](https://github.com/ldotlopez/ha-ideenergy/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/ldotlopez/ha-ideenergy/workflows/Validate%20with%20HACS/badge.svg)](https://github.com/ldotlopez/ha-ideenergy/actions/workflows/hacs.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

[ideenergy](https://github.com/ldotlopez/ideenergy) integration for [home-assistant](home-assistant.io/)

This integration provides sensors for spanish energy distributor [i-DE](i-de.es).
Requires an **advanced** user on the distributors's website.

**⚠️ Make sure to read the 'warning' section**

## Features

* Integration with the HomeAssistant energy panel.
* Support for various contracts.
* Accumulated consumption sensor.
* Experimental sensor of historical consumption data with better (sub-kWh) precession.
* Configuration through the [HomeAssistant web interface](https://developers.home-assistant.io/docs/config_entries_options_flow_handler) without the need to edit YAML files.
* Update algorithm to read the ICP near the end of each hourly period (between minute 50 and 59) with a better representation of consumption in the HomeAssistant energy panel.
* Fully [asynchronous](https://developers.home-assistant.io/docs/asyncio_index) and integrated with HomeAssistant.

## Instalation

Through `custom_components` or [HACS](https://hacs.xyz/)

## Snapshots

*Accumulated energy sensor*

![snapshot](screenshots/accumulated.png)

*Historical energy sensor*

![snapshot](screenshots/historical.png)

*Configuration wizard*

![snapshot](screenshots/configuration-1.png)
![snapshot](screenshots/configuration-2.png)

## Warnings
This extension provides an 'historical' sensor to incorporate data from the past into Home Assistant database. For your own safety the sensor is not enabled by default and must be enabled manually.

☠️ Historic sensor is based on a **high experimental hack** and can broke and/or corrupt your database and/or statistics. **Use at your own risk**.

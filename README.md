# home-assistant ideenergy

[ideenergy](https://github.com/ldotlopez/ideenergy) integration for [home-assistant](home-assistant.io/)

This integration provides sensors for spanish energy distributor [i-de](i-de.es).
Requires an **advanced** user on the distributors's website.

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

Warning: i-de "API" is not very reliable and sometimes it is not possible to access the meter reading. This integration checks the meter once every hour, retrying the reading up to 3 times if it fails. It is advised to leave the extension enabled overnight or for a few hours to get good results.

## Snapshots

*Accumulated energy sensor*

![snapshot](screenshots/accumulated.png)

*Historical energy sensor*

![snapshot](screenshots/historical.png)

*Configuration wizard*

![snapshot](screenshots/configuration-1.png)
![snapshot](screenshots/configuration-2.png)
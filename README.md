# home-assistant ideenergy

[ideenergy](https://github.com/ldotlopez/ideenergy) integration for [home-assistant](home-assistant.io/)

This integration provides sensors for spanish energy distributor [i-de](i-de.es).
Requires an **advanced** user on the distributors's website.

![snapshot](snapshot.png)


## Features

* Support for various contracts.
* Accumulated consumption sensor.
* Experimental sensor of historical consumption data.
* Configuration through the [HomeAssistant web interface](https://developers.home-assistant.io/docs/config_entries_options_flow_handler) without the need to edit YAML files.
* Fully [asynchronous](https://developers.home-assistant.io/docs/asyncio_index) and integrated with HomeAssistant.
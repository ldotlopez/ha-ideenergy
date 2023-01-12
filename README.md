# i-DE (Iberdrola Distribución) Custom Integration for Home Assistant

<!-- HomeAssistant badges -->
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![hassfest validation](https://github.com/ldotlopez/ha-ideenergy/workflows/Validate%20with%20hassfest/badge.svg)](https://github.com/ldotlopez/ha-ideenergy/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/ldotlopez/ha-ideenergy/workflows/Validate%20with%20HACS/badge.svg)](https://github.com/ldotlopez/ha-ideenergy/actions/workflows/hacs.yml)

<!-- Code and releases -->
![GitHub Release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/ldotlopez/ha-ideenergy?include_prereleases)
[![CodeQL](https://github.com/ldotlopez/ha-ideenergy/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/ldotlopez/ha-ideenergy/actions/workflows/codeql-analysis.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

[ideenergy](https://github.com/ldotlopez/ideenergy) integration for [home-assistant](https://home-assistant.io/)

i-DE (Iberdrola Distribución) Custom Integration for Home Assistant, providing sensors for Spanish Energy Distributor [i-DE](https://i-de.es).

This integration requires an **advanced** user profile on i-DE website.

**⚠️ Make sure to read the 'Remarks', 'Dependencies' and 'Warning' sections**

## Features

* Integration with the Home Assistant Energy Panel.
* Support for several contracts.
* Accumulated consumption sensor.
* Experimental sensor for historical consumption data with better (sub-kWh) precision. Same data as available on i-DE website. This data is not realtime and usually has a 24-hour to 48-hour offset.
* Configuration through [Home Assistant Interface](https://developers.home-assistant.io/docs/config_entries_options_flow_handler) without the need to edit YAML files.
* Update algorithm to read the ICP near the end of each hourly period (between minute 50 and 59) with a better representation of consumption in the Home Assistant energy panel.
* Fully [asynchronous](https://developers.home-assistant.io/docs/asyncio_index) and integrated with HomeAssistant.

### Remarks
* The reading is done directly to your meter. Due to connectivity issues or i-DE server issues, you may not always obtain readings as expected. Keep in mind that sometimes a delay on the reading may occurr.
* The reading only returns integer values. If from the last reading your meter indicates a variance minor then 1 kWh, the integration will not reflect any variance and that will only be recorded once the variance from the previous reading is greater then 1.
* Solar Production (if applies on your case) is under development. 


### Dependencies

You must have an i-DE username and access to the Clients' website. You may register here: [Área Clientes | I-DE - Grupo Iberdrola](https://www.i-de.es/consumidores/web/guest/login).

It also necessary to have an "Advanced User" profile. Should you not have one already, you need to fill the request for from your [Profile Area](https://www.i-de.es/consumidores/web/home/personal-area/userData).

## Installation

### Using [HACS](https://hacs.xyz/) (recommended)

- Copy this repo URL
- In the HACS section, add this repo as a custom one:

  ![Custom repository](https://user-images.githubusercontent.com/59612788/171965822-4a89c14e-9eb2-4134-8de2-1d3f380663e4.png)
  
  - On the "Repository" field put the URL copied before
  - On the "Category" select "Integration"
  - Click the "Download" button and download latest version. 
- Restart HA
- Click this button >>
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ideenergy)
- or Go to "Settings" >> "Devices & Services" and click "+ ADD INTEGRATION" and select "i-de.es energy sensors"  
![image](https://user-images.githubusercontent.com/59612788/171966005-e58f6b88-a952-4033-82c6-b1d4ea665873.png)
- Follow the configuration steps: provide your credentials for access to i-DE and select the contract that you want to monitor. (Should you need to add more contracts, just follow the previous step as many times as needed).


### Manually

- Download/clone this repo
- Copy the [custom_components/ide](custom_components/ideenergy) folder into your custom_components folder into your HA installation
- Restart HA
- Click this button >>
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ideenergy)
- or Go to "Settings" >> "Devices & Services" and click "+ ADD INTEGRATION" and select "i-de.es energy sensors" 
![image](https://user-images.githubusercontent.com/59612788/171966005-e58f6b88-a952-4033-82c6-b1d4ea665873.png)
- Follow the configuration steps: provide your credentials for access to i-DE and select the contract that you want to monitor. (Should you need to add more contracts, just follow the previous step as many times as needed).

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

## License

This project is licensed under the GNU General Public License v3.0 License - see the LICENSE file for details


## Disclaimer

THIS PROJECT IS NOT IN ANY WAY ASSOCIATED WITH OR RELATED TO THE IBERDROLA GROUP COMPANIES OR ANY OTHER. The information here and online is for educational and resource purposes only and therefore the developers do not endorse or condone any inappropriate use of it, and take no legal responsibility for the functionality or security of your devices.

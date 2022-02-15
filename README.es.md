# home-assistant ideenergy

Integración [ideenergy](https://github.com/ldotlopez/ideenergy) para [home-assistant](home-assistant.io/)

Esta integración provee sensores para el distribuidor de energía español [i-de](i-de.es).
Require de un usuario **avanzado** en la página web del distribuidor.

![snapshot](snapshot.png)


## Características

* Soporte para varios contratos.
* Sensor de consumo acumulado.
* Sensor experimental de datos históricos de consumo.
* Configuración a través del [interfaz web de HomeAssistant](https://developers.home-assistant.io/docs/config_entries_options_flow_handler) sin necesidad de editar ficheros YAML.
* Totalmente [asíncrono](https://developers.home-assistant.io/docs/asyncio_index) e integrado en HomeAssistant.
# home-assistant ideenergy

Integración [ideenergy](https://github.com/ldotlopez/ideenergy) para [home-assistant](home-assistant.io/)

Esta integración provee sensores para el distribuidor de energía español [i-de](i-de.es).
Require de un usuario **avanzado** en la página web del distribuidor.


## Características

* Integración con el panel del energía de HomeAssistant
* Soporte para varios contratos.
* Sensor de consumo acumulado.
* Sensor experimental de datos históricos de consumo con mayor (sub-kWh) precesión.
* Configuración a través del [interfaz web de HomeAssistant](https://developers.home-assistant.io/docs/config_entries_options_flow_handler) sin necesidad de editar ficheros YAML.
* Algoritmo de actualización para leer el contador cerca del final de cada periodo horario (entre el minuto 50 y 59) y una mejor representación del consumo en el panel de energía de HomeAssistant
* Totalmente [asíncrono](https://developers.home-assistant.io/docs/asyncio_index) e integrado en HomeAssistant.


## Instalación

A través de custom_components o [HACS](https://hacs.xyz/)

## Capturas

*Sensor de energía acumulada*
![snapshot](screenshots/accumulated.png)

*Sensor de histórico de energía*

![snapshot](screenshots/historical.png)

*Asistente de configuración*

![snapshot](screenshots/configuration-1.png)
![snapshot](screenshots/configuration-2.png)
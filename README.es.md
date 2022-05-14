# home-assistant ideenergy

Integración [ideenergy](https://github.com/ldotlopez/ideenergy) para [home-assistant](home-assistant.io/)

Esta integración provee sensores para el distribuidor de energía español [i-DE](i-de.es).
Require de un usuario **avanzado** en la página web del distribuidor.

**⚠️ Asegurese de leer la sección 'Advertencias'**

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

## Advertencias
Esta integración provee un sensor 'histórico' que incorpora datos del pasado en la base de datos de Home Assistant. Por su propia seguridad este sensor no está habilitado y debe activarse manualmente.

☠️ El sensor histórico está basado en un **hack extremadamente experimental** y puede romper y/o corromper su base de datos y/o estadísticas. **Use lo bajo su propio riesgo**.

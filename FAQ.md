# FAQ

## Q. Why "X" doesn't work

A. Most features in this integration are experimental. If it's not listed as supported it's **not** supported. Double-check this.


## Q. Accumulated (or instant) consumption sensor is in an unknown state or doesn't show any data.


A. Due to connectivity issues or i-DE server issues, you may not always obtain readings as expected. Keep in mind that sometimes a delay on the reading may occurr.

Those two sensors read data directly from your service point. The i-de API for this data is **very** unreliable, > 50% of the calls fail. We try out best to circumvent this situation but we can't do magic.

Also, due to connectivity issues or i-DE server issues, you may not always obtain readings as expected.

Give it some time, two or three days, before filing a bug.


## Q. Why accumulated (or instant) consumption sensors are only updated once at hour? Can be this interval shorter?

These sensors need to read the service point directly.

The i-de.es service point API is not very reliable, we try up to three calls before giving up in each update window (interval 50-59 of each hour).

On the other hand, the i-de.es platform blocks users if the service point is queried your user if he queries the service point too often. In our experience, no more than 5-6 calls in 10 minutes.

The policy of updating the sensors only once an hour is given by the sum of these two situations.

## Q. Accumulated (or instant) consumption sensor shows 0 increment at some intervals.

A. Readings from this sensors only returns integer values. If from the last reading your meter indicates a variance minor then 1 kWh, the integration will not reflect any variance and that will only be recorded once the variance from the previous reading is greater then 1.


## Q. Historical sensors (consumption and generation) doesn't have a value

A. They are not supposed to. Historical sensors are a hack, HomeAssistant is not supposed to have historical sensors.

Historical sensors can't provide the current state, Home Assistant will show "undefined" state forever, it's OK and intentional. To view historical data you have to go [History](https://my.home-assistant.io/redirect/history/) → Select any historical sensor →  Go back some days.

Keep in mind that historical data has a ~24h delay.

Until 1.1.0 those sensors doen't generate statistic data. You need this data to them as an energy source in the energy panel.

Before 1.1.0 you have to use the "Accumulated consumption" sensor as a source for the energy panel.

## Q. I have a problem with multiple contracts: I got banned/Doesn't work

We recommend disabling the "Accumulated" and "Instant" sensors if you have multiple contracts.

Due to some issues with the API and rate limit it's very possible that i-de bans you have a few hours of running this integration.

**Important**: Having multiple contracts it's different of having **configured** multiple contracts. You can have multiple contracts but have only one configured in Home Assistant, or you can have multiple contracts added in HomeAssistant but only one (or none) with mentioned sensors enabled.

If you have multiple contracts I recommend you to only enable historical sensors.

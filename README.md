# brandstofScout
brandstofScout is a python script that scout the cheapest fuel in the Netherlands (based on given coordinates) for your beloved vehicle and logs it in InfluxDB and makes it available in HomeAssistant


# Getting started

- Clone the repo
- Rename the .env.example to .env
- Populate the .env with your own secrets
- Run the Docker Compose file: ```sudo docker compose down && sudo docker compose build && sudo docker compose up -d```
- Run ```sudo docker compose logs -f brandstof-scout``` to view its logs
- Check in InfluxDB and Home assistant if the new values are being added
- Download the logos of the fuel companies in your area and place the in the following homeassistant directory: ```home_assistant/www/fuelstations/logos```
- The logos should be named for example: esso.png, for the all fuel stations with the Esso brand.


- For Home assistant add the following dashboard:
```
  - type: sections
    title: Brandstof
    path: brandstof
    icon: mdi:gas-station
    sections:
      - type: grid
        cards:
          - type: vertical-stack
            cards:
              - type: markdown
                title: ⛽ Top 3 goedkoopste EURO98 stations
                content: |
                  {% for i in [1, 2, 3] %}
                    {% set s = states("sensor.cheapest_fuel_station_euro98_" ~ i) %}
                    {% set name = state_attr("sensor.cheapest_fuel_station_euro98_" ~ i, "station_name") %}
                    {% set city = state_attr("sensor.cheapest_fuel_station_euro98_" ~ i, "city") %}
                    {% set logo = state_attr("sensor.cheapest_fuel_station_euro98_" ~ i, "logo") %}
                    **{{ i }}.** <img src="{{ logo }}" width="80" style="vertical-align: middle;"> 
                    {{ name }} ({{ city }}) — €{{ s }}  
                    <br>
                  {% endfor %}
          - type: heading
            heading_style: title
      - type: grid
        cards:
          - type: vertical-stack
            cards:
              - type: markdown
                title: ⛽ Top 3 goedkoopste EURO95 stations
                content: |
                  {% for i in [1, 2, 3] %}
                    {% set s = states("sensor.cheapest_fuel_station_euro95_" ~ i) %}
                    {% set name = state_attr("sensor.cheapest_fuel_station_euro95_" ~ i, "station_name") %}
                    {% set city = state_attr("sensor.cheapest_fuel_station_euro95_" ~ i, "city") %}
                    {% set logo = state_attr("sensor.cheapest_fuel_station_euro95_" ~ i, "logo") %}
                    **{{ i }}.** <img src="{{ logo }}" width="80" style="vertical-align: middle;"> 
                    {{ name }} ({{ city }}) — €{{ s }}  
                    <br>
                  {% endfor %}
          - type: heading
            heading_style: title
      - type: grid
        cards:
          - type: vertical-stack
            cards:
              - type: markdown
                title: ⛽ Top 3 goedkoopste AUTOGAS stations
                content: |
                  {% for i in [1, 2, 3] %}
                    {% set s = states("sensor.cheapest_fuel_station_autogas_" ~ i) %}
                    {% set name = state_attr("sensor.cheapest_fuel_station_autogas_" ~ i, "station_name") %}
                    {% set city = state_attr("sensor.cheapest_fuel_station_autogas_" ~ i, "city") %}
                    {% set logo = state_attr("sensor.cheapest_fuel_station_autogas_" ~ i, "logo") %}
                    **{{ i }}.** <img src="{{ logo }}" width="80" style="vertical-align: middle;"> 
                    {{ name }} ({{ city }}) — €{{ s }}  
                    <br>
                  {% endfor %}
    cards: []
```
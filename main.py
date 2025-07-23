import requests
import urllib.parse
import datetime

import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import os
from envLogos import* #import logo info

#InfluxDB
INFLUXDB_TOKEN = os.environ['SECRET_INFLUX_TOKEN']
org = os.environ['SECRET_INFLUX_ORG']
url = os.environ['SECRET_INFLUX_URL']
bucket= os.environ['SECRET_INFLUX_BUCKET']

influxClient = influxdb_client.InfluxDBClient(url=url, token=INFLUXDB_TOKEN, org=org)

#Home Assistant
HA_URL = os.environ['SECRET_HOMEASSISTANT_URL']
HA_TOKEN = os.environ['SECRET_HOMEASSISTANT_TOKEN']


STATION_LOGOS = envLogos

apiKeyAnwb = 'NOT-NEEDED'

lat_min = os.environ['SECRET_LAT_MIN']
lon_min = os.environ['SECRET_LON_MIN']
lat_max = os.environ['SECRET_LAT_MAX']
lon_max = os.environ['SECRET_LON_MAX']
bounding_box = [lat_min, lon_min, lat_max, lon_max]

# Encode bounding box for the API query
bbox_param = '%2C'.join(map(str, bounding_box))

topCheapestStations = os.environ['TOP_CHEAPEST_STATIONS']

stations = []

# Construct the URL with query parameters
urlANWB = (
    "https://api.anwb.nl/routing/points-of-interest/v3/all?"
    f"type-filter=FUEL_STATION"
    f"&bounding-box-filter={bbox_param}"
    f"&view=FULL"
    f"&api_key={apiKeyAnwb}"
)

def main():
    print(f"Script executed at {datetime.datetime.now()}")
    # delete_all_data_from_bucket()
    reqAnwbData()
    # createTestStation()
    push2Influx()
    
    fuel_types_raw = os.getenv("FUELTYPE_OF_INTEREST_HA", "")
    selectedFuelTypes = set(fuel_types_raw.split(",")) if fuel_types_raw else set()

    print("Fuel types of interest:", selectedFuelTypes)
    for fuelTypes in selectedFuelTypes:
        print(f"Fueltype: ", fuelTypes)
        push2HomeAssistant(topCheapestStations, fuelTypes)

    influxClient.close()


# Returns the topX cheapest stations
def push2HomeAssistant(topX, fuelType): 
    query_api = influxClient.query_api()
    #Query the top topX cheapest stations
    flux_query =("""
    from(bucket: "fuel_prices")
        |> range(start: today())
        |> filter(fn: (r) => r._field == "price" or r._field == "latitude" or r._field == "longitude")
        |> filter(fn: (r) => r.fuel_type == "{0}")
        |> aggregateWindow(every: 1d, fn: min, createEmpty: false)
        |> group(columns: ["station_name", "city", "fuel_type"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> group(columns: [])
        |> sort(columns: ["price"])
        |> limit(n: 2)
        |> keep(columns: ["price", "station_name", "city", "fuel_type", "latitude", "longitude"])
    """.format(str(fuelType), topX))


    result = query_api.query(flux_query)
    records = result[0].records if result else []

    #Format data and push the individual stations
    for i, record in enumerate(records, start=1):
        station = {
            "station_name": record["station_name"],
            "city": record["city"],
            "lat": record["latitude"],
            "lon": record["longitude"],
            "fuel_type": record["fuel_type"],
            "price": record["price"],
            "logo": getStationLogo(record["station_name"])
        }
        pushStationHomeAssistant(i, station, fuelType)

#Push individual stations to HomeAssistant
def pushStationHomeAssistant(index, station, fuelType):
    print("Pushing to home assistant")
    entity_id = f"sensor.cheapest_Fuel_station_{fuelType}_{index}"
    url = f"{HA_URL}/api/states/{entity_id}"

    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "state": round(station['price'], 3),
        "attributes": {
            "station_name": station["station_name"],
            "city": station["city"],
            "lat": station["lat"],
            "lon": station["lon"],
            "fuel_type": station["fuel_type"],
            "logo": station["logo"],
            "unit_of_measurement": "€",
            "friendly_name": f"{station['station_name']} - {station['city']} - {fuelType}",
            "custom_group": "fueltracker"
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code not in (200, 201):
        print(f"Failed to push {entity_id}: {response.status_code} — {response.text}")
    else:
        print(f"Pushed {entity_id}: {station['station_name']} - €{station['price']}")

#Find name of the associated logo
def getStationLogo(station_name):
    normalized_name = station_name.lower()
    for brand in STATION_LOGOS:
        if brand.lower() in normalized_name:
            print(f"Matched '{brand}' in '{station_name}'")
            return STATION_LOGOS[brand]
    print(f"No logo found for '{station_name}', using fallback")
    return "/local/fuelstations/logos/unknown.png"


#Request the ANWB data
def reqAnwbData():

    response = requests.get(urlANWB)

    # Check for a successful response
    if response.status_code == 200:
        response_json = response.json()
        # print(response_json)

        # Transform into a clean list of dictionaries
        for item in response_json["value"]:
            station = {
                "id": item["id"],
                "name": f"{item['title']}, {item['address']['streetAddress']}",
                "latitude": item["coordinates"]["latitude"],
                "longitude": item["coordinates"]["longitude"],
                "address": f"{item['address']['streetAddress']}, {item['address']['postalCode']} {item['address']['city']}",
                "fuel_prices": {p["fuelType"]: p["value"] for p in item.get("prices", [])},
                "opening_hours": {
                    day["dayOfWeek"][0]: f"{day['opens']} - {day['closes']}" for day in item.get("openingHours", [])
                }
            }
            stations.append(station)
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        print(response.text)

#Push the data to influx for long storing
def push2Influx():

    #Write date to influxDB
    write_api = influxClient.write_api(write_options=SYNCHRONOUS)

    for s in stations:
        for fuel, price in s["fuel_prices"].items():
            point = (
                Point("fuel_station_price")
                .tag("station_name", s["name"])
                .tag("fuel_type", fuel)
                .tag("city", s["address"].split()[-1])
                .field("price", price)
                .field("latitude", round(float(s["latitude"]), 8))
                .field("longitude", round(float(s["longitude"]), 8))
                .time(datetime.datetime.utcnow(), WritePrecision.NS)
            )
            write_api.write(bucket=bucket, org=org, record=point)

def createTestStation():
    station = {
        "id": "TEST123",
        "name": "Test Fuel Station",
        "latitude": 52.1561,
        "longitude": 5.3878,
        "address": "Teststraat 1, 1234AB Teststad",
        "fuel_prices": {
            "EURO98": 1.000,
        },
        "opening_hours": {
            "Monday": "00:00 - 23:59"
        }
    }
    stations.append(station)

if __name__=="__main__":
    main()

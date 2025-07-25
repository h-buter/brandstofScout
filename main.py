import requests
import urllib.parse
import datetime

import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import plotext as plt

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

trendDays = os.environ['TREND_DAYS']
trendDays = list(map(int, trendDays.split(',')))

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
    # # delete_all_data_from_bucket()
    # reqAnwbData()
    # # createTestStation()
    # push2Influx()
    
    # fuel_types_raw = os.getenv("FUELTYPE_OF_INTEREST_HA", "")
    # selectedFuelTypes = set(fuel_types_raw.split(",")) if fuel_types_raw else set()

    # print("Fuel types of interest:", selectedFuelTypes)
    # for fuelTypes in selectedFuelTypes:
    #     print(f"Fueltype: ", fuelTypes)
    #     push2HomeAssistant(topCheapestStations, fuelTypes)

    for days in trendDays:
        trend = priceTrend(days, "EURO95")
        if trend != None:
            pushTrendHomeAssistant(trend, days, "EURO95")

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

#Push trend to HomeAssistant
def pushTrendHomeAssistant(trend, days, fuelType):
    trend = trend * 100 #Convert to percentage
    entity_id = f"sensor.trend_{days}_{fuelType}"
    url = f"{HA_URL}/api/states/{entity_id}"

    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "state": trend,
        "attributes": {
            "unit_of_measurement": "%",
            "friendly_name": f"trend - {days}-days - {fuelType}",
            "custom_group": "fueltracker"
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code not in (200, 201):
        print(f"Failed to push {entity_id}: {response.status_code} — {response.text}")
    else:
        print(f"Pushed {entity_id}: trend of {days} days: {trend:.1f}% to HomeAssistant")

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

def priceTrend(days, fuelType):
    sum = 0.0
    array = {}
    for i in range(0, days, 1):
        # print("day: ", i)
        x = reqCheapestPriceOnDay(fuelType, i)
        # print(x)
        if (x == None):
            print(f"Not enough data for {days} days trend")
            return None
        else:
            array[i] = x
    trend = calculateRegressionTrend(array)
    return trend

    

def calculateRegressionTrend(array):
    array = [1.90, 1.95, 1.95, 1.80, 1.82, 1.83, 1.90, 1.96, 2.00, 2.10]
    length = len(array)
    yAvg = 0
    for i in range(0, length, 1):
        yAvg += array[i]
        # print(array[i])
    yAvg = yAvg / length

    xAvg = 0.5 * length * (length + 1) / length

    #sum of (xi - avg(x))*(yi - avg(y))
    numerator = 0
    for i in range(0, length, 1):
        # print(f"i {i+1}")
        z = (i + 1 - xAvg) * (array[i] - yAvg)
        numerator += z
    
    #sum of (xi - avg(x))^2
    denominator = 0
    for i in range(0, length, 1):

        denominator += pow(((i + 1) - xAvg), 2)

    m = numerator / denominator
    b = yAvg - m * xAvg
    trend = m * length / yAvg

    # print(f"m: {m}, b: {b}, trend: {trend}")
    # print(f"Trend for {length} days is: {trend:.6f}, {trend*100:.3f}%")

    plotPrices(array, m, b)
    return trend


def plotPrices(array, m, b):
    length = len(array)
    x = list(range(length))
    y = array
    regression_line = [m * xi + b for xi in x]

    # Calculate nice full number ticks for X and Y
    y_min = min(min(y), min(regression_line))
    y_max = max(max(y), max(regression_line))
    
    y_tick_min = int(y_min * 100) // 1 / 100  # Round down to 0.01
    y_tick_max = int(y_max * 100 + 1) // 1 / 100  # Round up to 0.01
    y_ticks = [round(tick, 2) for tick in plotext_range(y_tick_min, y_tick_max, 0.05)]

    plt.clear_figure()
    plt.plot_size(100, 30)
    plt.title("Prices (dots) and Regression Line")

    # Bigger dots
    plt.scatter(x, y, marker='■', color='cyan')
    plt.plot(x, regression_line, color='red')

    # Force axis ticks to use clean full numbers
    plt.xticks(x)  # Use exact integer steps for days
    plt.yticks(y_ticks)

    plt.xlabel("Day")
    plt.ylabel("Price")
    plt.show()

def plotext_range(start, stop, step):
    # Avoid floating point issues in range
    ticks = []
    while start <= stop:
        ticks.append(start)
        start = round(start + step, 4)
    return ticks

def reqCheapestPriceOnDay(fuelType, daysPast):
    begin = f"-{daysPast + 1}d"
    end = f"-{daysPast}d"

    query_api = influxClient.query_api()
    flux_query =f"""
    from(bucket: "fuel_prices")
        |> range(start: {begin}, stop: {end})
        |> filter(fn: (r) => r._field == "price")
        |> filter(fn: (r) => r.fuel_type == "{fuelType}")
        |> aggregateWindow(every: 1d, fn: min, createEmpty: false)
        |> group(columns: ["station_name", "city", "fuel_type"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> group(columns: [])
        |> sort(columns: ["price"])
        |> limit(n: 1)
        |> keep(columns: ["price", "station_name", "city", "fuel_type", "_time"])
    """


    result = query_api.query(flux_query)
    records = result[0].records if result else []

    if not records:
        return None  # No data found

    return records[0]["price"]


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

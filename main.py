import requests
import urllib.parse
import datetime

import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import plotext as pltTui

import os
from envLogos import* #import logo info

import matplotlib.pyplot as pltGui

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

fuel_types_raw = os.getenv("FUELTYPE_OF_INTEREST_HA", "")
selectedFuelTypes = set(fuel_types_raw.split(",")) if fuel_types_raw else set()

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
    reqAnwbData()
    # createTestStation()
    push2Influx()
    
    print("Fuel types of interest:", selectedFuelTypes)
    for fuelTypes in selectedFuelTypes:
        print(f"Fueltype: ", fuelTypes)
        push2HomeAssistant(topCheapestStations, fuelTypes)
        for days in trendDays:
            trend = priceTrend(days, fuelTypes)
            if trend != None:
                pushTrendHomeAssistant(trend, days, fuelTypes)

    influxClient.close()


# Returns the topX cheapest stations
def push2HomeAssistant(topX, fuelType): 
    query_api = influxClient.query_api()
    #Query the top topX cheapest stations
    flux_query =("""
    from(bucket: "fuel_prices")
        |> range(start: -1h)
        |> filter(fn: (r) => r._field == "price" or r._field == "latitude" or r._field == "longitude")
        |> filter(fn: (r) => r.fuel_type == "{0}")
        |> aggregateWindow(every: 1d, fn: min, createEmpty: false)
        |> group(columns: ["station_name", "city", "fuel_type"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> group(columns: [])
        |> sort(columns: ["price"])
        |> limit(n: {1})
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
    if (station['price'] == 0):
        print(f"{station['station_name']} - {station['price']} is unknown or has a null value, omitting this data entry")
    else:
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
    entity_id = f"sensor.trend_{fuelType}_{days}" 
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
            # print(f"Matched '{brand}' in '{station_name}'")
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
            name = s["name"]
            # print(f"price {name} - {price}")
            if (price == 0):
                print(f"{name} - {price} is unknown or has a null value, omitting this data entry")
            else:
                point = (
                    Point("fuel_station_price")
                    .tag("station_name", s["name"])
                    .tag("fuel_type", fuel)
                    .tag("city", s["address"].split()[-1])
                    .field("price", float(price))
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
            array[days - 1 - i] = x #invert array so that most past date is first
    trend = calculateRegressionTrend(array, fuelType)
    return trend


def calculateRegressionTrend(array, fuelType):
    # array = [2.10, 2.00, 1.80, 1.90, 1.90, 1.80, 1.75, 1.80, 1.50, 1.40]
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

    plotPrices(array, m, b, fuelType, trend)
    plotPrices2Png(array, m, b, fuelType, trend)
    return trend


def plotPrices(array, m, b, fuelType, trend):
    import plotext as pltTui

    # Handle dict input
    if isinstance(array, dict):
        array = [array[k] for k in sorted(array.keys())]

    length = len(array)
    x = list(range(length))
    y = array
    regression_line = [m * xi + b for xi in x]

    # Determine Y-axis ticks with clean formatting
    y_min = min(min(y), min(regression_line))
    y_max = max(max(y), max(regression_line))
    
    y_tick_min = round((int(y_min / 0.05) * 0.05), 2)
    y_tick_max = round(((int(y_max / 0.05) + 1) * 0.05), 2)
    y_ticks = plotext_range(y_tick_min, y_tick_max, 0.05)

    # Clear and set up plot
    pltTui.clear_figure()
    pltTui.plot_size(100, 30)
    pltTui.title(f"{fuelType} fuel prices over {length} days")

    pltTui.scatter(x, y, marker='■', color='cyan', label="Prices")
    pltTui.plot(x, regression_line, color='red', label=f"Trend: {trend*100:.2f}%")

    # Set ticks and labels
    pltTui.xticks(x)
    pltTui.yticks(y_ticks)

    pltTui.xlabel("Day")
    pltTui.ylabel("Price")

    pltTui.show()

def plotext_range(start, stop, step):
    # Avoid floating-point issues in range
    ticks = []
    while start <= stop:
        ticks.append(round(start, 2))
        start = round(start + step, 4)
    return ticks

def plotPrices2Png(array, m, b, fuelType, trend, output_dir="/app/plots"):
    # Handle dict input
    if isinstance(array, dict):
        array = [array[k] for k in sorted(array.keys())]

    y = array
    x = list(range(len(y)))

    if len(x) != len(y):
        print(f"Cannot plot: x = {len(x)}, y = {len(y)}")
        return

    regression_line = [m * xi + b for xi in x]

    fig, ax = pltGui.subplots(figsize=(10, 4))

    # # Set black background
    # fig.patch.set_facecolor('black')
    # ax.set_facecolor('black')

    for spine in ax.spines.values():
        spine.set_color('white')

    # Plot points and regression line
    ax.scatter(x, y, color='cyan', label="Prices", s=40)
    ax.plot(x, regression_line, color='red', label=f"Trend: {trend*100:.2f}%")

    # Set ticks and labels color to white
    ax.tick_params(colors='white')  # ticks
    ax.xaxis.label.set_color('white')  # x label
    ax.yaxis.label.set_color('white')  # y label

    # Set title color
    ax.set_title(f"{fuelType} fuel prices over {len(y)} days", color='white')
    pltGui.xlabel("Day")
    pltGui.ylabel("Price")

    # Set legend text color
    legend = ax.legend()
    for text in legend.get_texts():
        text.set_color('white')

    # Set ticks to integers for x axis
    ax.set_xticks(x)

    # Adjust subplot params to reduce left/right margin
    pltGui.subplots_adjust(left=0.07, right=0.99)

    # Save figure with transparent background
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{fuelType.lower()}_trend.png")
    pltGui.savefig(file_path, transparent=True)
    pltGui.close()

    print(f"Saved plot to {file_path}")

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

    # print(records[0]["price"])
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

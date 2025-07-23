import influxdb_client, os, time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import datetime

from projectSecrets import*

#InfluxDB

INFLUXDB_TOKEN = secretInfluxToken
org = secretInfluxOrg
url = secretInfluxUrl
bucket= secretInfluxBucket

influxClient = influxdb_client.InfluxDBClient(url=url, token=INFLUXDB_TOKEN, org=org)

delete_api = influxClient.delete_api()

# Delete everything from the beginning of time until now
start = "1970-01-01T00:00:00Z"
stop = datetime.datetime.utcnow().isoformat("T") + "Z"

try:
    delete_api.delete(start=start, stop=stop, predicate="", bucket=bucket, org=org)
    print(f"All data deleted from bucket '{bucket}'.")
except Exception as e:
    print(f"Failed to delete data: {e}")
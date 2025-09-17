import requests
from datetime import datetime, timedelta
import pandas as pd
from zoneinfo import ZoneInfo
from sklearn.linear_model import LinearRegression
import json
import os
from urllib.parse import quote
try:
    from pymodbus.client.sync import ModbusTcpClient
except ImportError:
    from pymodbus.client import ModbusTcpClient
import argparse
import logging
import time
import paho.mqtt.client as mqtt
import pickle
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument("--ha_url", required=False, default="http://supervisor/core")
parser.add_argument("--ha_token", required=False, default="")
parser.add_argument("--system_size_kw", type=float, required=True)
parser.add_argument("--battery_size_kwh", type=float, required=True)
parser.add_argument("--minimum_soc_percent", type=float, required=True)
parser.add_argument("--minimum_soc_by_sunset", type=float, required=True)
parser.add_argument("--cheap_power_window_start", required=True)
parser.add_argument("--cheap_power_window_end", required=True)
parser.add_argument("--fronius_host", required=True)
parser.add_argument("--cache_forecast", type=bool, required=False, default=True)
parser.add_argument("--cache_duration", type=int, required=False, default=120)
parser.add_argument("--battery_charge_efficiency", type=int, default=95)
parser.add_argument("--ha_days_to_retrieve", type=int, default=30)
parser.add_argument("--HA_battery_charge_rate_sensor", type=str, default="sensor.solarnet_power_battery_charge")
parser.add_argument("--HA_battery_SOC_sensor", type=str, default="sensor.byd_battery_box_premium_hv_state_of_charge")
parser.add_argument("--HA_power_usage_sensor", type=str, default="sensor.solarnet_power_load_consumed")
parser.add_argument("--mqtt_broker", default="mqtt://core-mosquitto", help="MQTT broker URL")
parser.add_argument("--mqtt_broker_port", type=int, default=1883, help="MQTT broker port")
parser.add_argument("--mqtt_topic_prefix", default="solar_forecast", help="MQTT topic prefix for publishing data")
parser.add_argument("--mqtt_username", default="", help="MQTT username")
parser.add_argument("--mqtt_password", default="", help="MQTT password")
parser.add_argument("--max_battery_charge_rate", type=int, default=5000, help="Maximum battery charge rate in watts")

# Only parse arguments if running as main script
if __name__ == "__main__":
    args = parser.parse_args()
else:
    # Create dummy args object for imports
    import argparse
    args = argparse.Namespace()


# Get Home Assistant API token from add-on environment
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
if not SUPERVISOR_TOKEN:
    print("No Supervisor token found")

# --- Configuration from Arguments ---
HA_URL = args.ha_url
HA_TOKEN = args.ha_token if args.ha_token else SUPERVISOR_TOKEN
SYSTEM_SIZE_KW = args.system_size_kw
BATTERY_SIZE_KWH = args.battery_size_kwh
MINIMUM_SOC_PERCENT = args.minimum_soc_percent
MINIMUM_SOC_BY_SUNSET = args.minimum_soc_by_sunset
CHEAP_POWER_WINDOW = (args.cheap_power_window_start, args.cheap_power_window_end)
FRONIUS_HOST = args.fronius_host
USE_SOLAR_CACHE = args.cache_forecast
SOLAR_CACHE_DURATION = args.cache_duration
BATTERY_CHARGE_EFFICIENCY = args.battery_charge_efficiency / 100.0  # Convert percentage to a decimal
DAYS_OF_HA_POWER_HISTORY = args.ha_days_to_retrieve  # Days of Home Assistant power history to fetch
HA_BATTERY_CHARGE_RATE_SENSOR = args.HA_battery_charge_rate_sensor
HA_BATTERY_SOC_SENSOR = args.HA_battery_SOC_sensor
HA_POWER_USAGE_SENSOR = args.HA_power_usage_sensor
MAX_BATTERY_CHARGE_RATE = args.max_battery_charge_rate


# --- Configuration ---
headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

entity_ids = [
    HA_BATTERY_CHARGE_RATE_SENSOR,
    HA_BATTERY_SOC_SENSOR,
    HA_POWER_USAGE_SENSOR
]

# Get Home Assistant configuration for latitude, longitude and timezone
api_endpoint = f"{HA_URL}/api/config"
response = requests.get(api_endpoint, headers=headers)
print(f"Fetching HA config from {api_endpoint}, Status Code: {response.status_code}")
HA_config_data = response.json()
LATITUDE = HA_config_data.get('latitude')
LONGITUDE = HA_config_data.get('longitude')
time_zone = HA_config_data.get('time_zone')
TIME_ZONE = quote(time_zone,safe='')
print(f"Latitude: {LATITUDE}, Longitude: {LONGITUDE}, Time Zone: {time_zone}")


# Replace cache file paths
ADDON_DATA_PATH = "/data"
SOLAR_CACHE_FILE = os.path.join(ADDON_DATA_PATH, "solar_forecast_cache.json")
STATE_FILE = os.path.join(ADDON_DATA_PATH, "charging_state.json")
HA_DATA_CACHE_FILE = os.path.join(ADDON_DATA_PATH, "ha_sensor_data.pickle")
HA_CACHE_DURATION = timedelta(hours=12)  # Cache for 12 hours

# Create data directory if it doesn't exist
os.makedirs(ADDON_DATA_PATH, exist_ok=True)

end_time = datetime.now()
start_time = end_time - timedelta(days=DAYS_OF_HA_POWER_HISTORY)


# --- Fetch Home Assistant Data ---
def get_cached_ha_data():
    """Retrieve cached Home Assistant sensor data if valid"""
    if not os.path.exists(HA_DATA_CACHE_FILE):
        return None

    try:
        with open(HA_DATA_CACHE_FILE, 'rb') as f:
            cache = pickle.load(f)

        cache_time = cache.get('timestamp')
        if cache_time and datetime.now() - cache_time < HA_CACHE_DURATION:
            logger.info("Using cached Home Assistant sensor data")
            return cache.get('data')
        else:
            logger.info("Cache expired, will fetch fresh data")

    except (pickle.UnpicklingError, EOFError, KeyError) as e:
        logger.error(f"Cache file corrupted, removing: {e}")
        try:
            os.remove(HA_DATA_CACHE_FILE)
        except OSError:
            pass
    except Exception as e:
        logger.error(f"Error reading cache: {e}")

    return None

def save_ha_data_cache(data):
    """Save Home Assistant sensor data to cache with compression"""
    try:
        cache = {
            'timestamp': datetime.now(),
            'data': data
        }
        with open(HA_DATA_CACHE_FILE, 'wb') as f:
            pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)  # Use highest compression
        logger.info(f"Saved {len(data)} records to cache")
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

all_sensor_data = get_cached_ha_data()

if all_sensor_data is None:
    logger.info("Fetching fresh Home Assistant sensor data")
    all_sensor_data = []

    for entity_id in entity_ids:
        api_endpoint = f"{HA_URL}/api/history/period/{start_time.isoformat()}?filter_entity_id={entity_id}&end_time={end_time.isoformat()}"
        try:
            response = requests.get(api_endpoint, headers=headers)
            response.raise_for_status()
            historical_data = response.json()

            # Process data immediately to reduce memory usage
            for state_list in historical_data:
                for state_entry in state_list:
                    entity = state_entry.get('entity_id')
                    state = state_entry.get('state')
                    timestamp = state_entry.get('last_updated')
                    # Only keep essential attributes to reduce memory
                    attributes = state_entry.get('attributes', {})
                    essential_attrs = {
                        'unit_of_measurement': attributes.get('unit_of_measurement'),
                        'device_class': attributes.get('device_class')
                    }
                    all_sensor_data.append({
                        "Entity": entity,
                        "State": state,
                        "Time": timestamp,
                        "Attributes": essential_attrs
                    })

            # Clear response data immediately
            del historical_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data: {e}")

    # Cache the fresh data
    save_ha_data_cache(all_sensor_data)
else:
    logger.info("Using cached Home Assistant sensor data")

# --- Convert to DataFrame with memory optimization ---
df = pd.DataFrame(all_sensor_data)
df["Entity"] = df["Entity"].str.strip().astype('category')  # Use category for repeated strings
df["State"] = pd.to_numeric(df["State"], errors="coerce", downcast='float')  # Downcast to smaller float
df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
df = df.dropna(subset=["Entity", "State", "Time"])

# Clear the large list from memory immediately
del all_sensor_data

# --- Determine sensor type from attributes ---
def get_sensor_type(attr):
    if not isinstance(attr, dict):
        return None
    unit = attr.get("unit_of_measurement", "").lower()
    device_class = attr.get("device_class", "")
    if unit == "w" or device_class == "power":
        return "power"
    elif unit == "wh" or device_class == "energy":
        return "energy"
    elif unit == "%" or device_class == "battery":
        return "soc"
    return None

df["SensorType"] = df["Attributes"].apply(get_sensor_type)

# --- Calculate Daily Energy Usage with memory optimization ---
results = {}
soc_stats = {}
latest_soc = None

for entity, group in df.groupby("Entity", observed=True):
    group = group.sort_values("Time")
    group["Date"] = group["Time"].dt.date
    sensor_type = group["SensorType"].iloc[0] if not group["SensorType"].isnull().all() else None

    if sensor_type == "power":
        group["Time_Diff"] = group["Time"].diff().dt.total_seconds().fillna(0)
        group["Energy_Wh"] = (group["State"] * group["Time_Diff"]) / 3600
        daily_energy = group.groupby("Date")["Energy_Wh"].sum()
        results[entity] = daily_energy
        # Clear intermediate calculations
        del group["Time_Diff"], group["Energy_Wh"]
    elif sensor_type == "soc":
        daily_min = group.groupby("Date")["State"].min()
        daily_max = group.groupby("Date")["State"].max()
        for date in daily_min.index:
            soc_stats[date] = {
                "min": float(daily_min[date]),  # Convert to float to save memory
                "max": float(daily_max[date])
            }
        latest_entry = group.iloc[-1]
        latest_soc = float(latest_entry["State"])

# Clear DataFrame from memory after processing
del df

# --- Prepare DataFrame for Forecasting with memory optimization ---
dates = sorted(set(results.get(HA_BATTERY_CHARGE_RATE_SENSOR, pd.Series()).index)
               & set(results.get(HA_POWER_USAGE_SENSOR, pd.Series()).index)
               & set(soc_stats.keys()))

# Build data more efficiently
forecast_data = []
for date in dates:
    battery_charge = results.get(HA_BATTERY_CHARGE_RATE_SENSOR, {}).get(date, 0)
    load_consumed = results.get(HA_POWER_USAGE_SENSOR, {}).get(date, 0)
    min_soc = soc_stats[date]["min"]
    max_soc = soc_stats[date]["max"]

    # Convert SOC delta from percentage to energy (kWh)
    soc_delta_percent = max_soc - min_soc
    soc_delta_kwh = (soc_delta_percent / 100.0) * BATTERY_SIZE_KWH

    forecast_data.append({
        "Date": pd.to_datetime(date),
        "Battery_Charge": float(battery_charge),
        "Load_Consumed": float(load_consumed),
        "Battery_Min_SOC": min_soc,
        "Battery_Max_SOC": max_soc,
        "SOC_Delta": soc_delta_percent,
        "SOC_Delta_kWh": soc_delta_kwh,
        "Power_Need": load_consumed - battery_charge + soc_delta_kwh * 1000,  # Convert kWh to Wh for consistency
        "DayOfWeek": pd.to_datetime(date).weekday()
    })

df_forecast = pd.DataFrame(forecast_data)

# Clear intermediate data structures
del results, soc_stats, forecast_data

# --- Forecast Power Need ---
X = df_forecast[["DayOfWeek"]]
y = df_forecast["Power_Need"]
model = LinearRegression()
model.fit(X, y)

# Create prediction DataFrame with same column name
next_day = df_forecast["Date"].max() + timedelta(days=1)
X_pred = pd.DataFrame([[next_day.weekday()]], columns=["DayOfWeek"])
predicted_power_need_wh = model.predict(X_pred)[0]
predicted_power_need_kwh = predicted_power_need_wh / 1000

# --- Solar Forecast with Optional Caching ---
def get_solar_forecast_advanced(latitude, longitude,time_zone, system_size_kw, cache_file, use_cache=True, cache_duration_minutes=120):
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&hourly=cloud_cover,shortwave_radiation,direct_normal_irradiance,diffuse_radiation"
        f"&timezone={time_zone}&past_days=0&forecast_days=1"
    )
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached = json.load(f)
                timestamp = cached.get("timestamp")
                if timestamp:
                    cache_time = datetime.fromisoformat(timestamp)
                    if datetime.now() - cache_time < timedelta(minutes=cache_duration_minutes):
                        logger.info("Using cached solar forecast data")
                        return cached.get("forecast", {})
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Solar forecast cache corrupted, removing: {e}")
            try:
                os.remove(cache_file)
            except OSError:
                pass
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch data: {e}"}
    if "hourly" not in data:
        return {"error": "No valid data received from API."}
    hourly = data["hourly"]
    timestamps = hourly.get("time", [])
    shortwave = hourly.get("shortwave_radiation", [])
    cloud_cover = hourly.get("cloud_cover", [])
    direct_normal = hourly.get("direct_normal_irradiance", [])
    diffuse = hourly.get("diffuse_radiation", [])
    avg_cloud_cover = sum(cloud_cover) / len(cloud_cover) if cloud_cover else 0
    avg_dni = sum(direct_normal) / len(direct_normal) if direct_normal else 0
    avg_diffuse = sum(diffuse) / len(diffuse) if diffuse else 0
    derating_factor = 0.7 if avg_cloud_cover > 80 else 1.0
    total_solar_kwh = sum((sw / 1000) * system_size_kw for sw in shortwave) * derating_factor
    forecast = {
        "timestamp": datetime.now().isoformat(),
        "forecast": {
            "total_solar_kwh": total_solar_kwh,
            "avg_cloud_cover": avg_cloud_cover,
            "avg_dni": avg_dni,
            "avg_diffuse": avg_diffuse,
            "hourly": {
                "time": timestamps,
                "shortwave_radiation": shortwave,
                "cloud_cover": cloud_cover,
                "direct_normal_irradiance": direct_normal,
                "diffuse_radiation": diffuse
            }
        }
    }
    with open(cache_file, "w") as f:
        json.dump(forecast, f, separators=(',', ':'))  # Compact JSON format
    return forecast["forecast"]

solar_forecast_data = get_solar_forecast_advanced(LATITUDE, LONGITUDE,TIME_ZONE, SYSTEM_SIZE_KW, SOLAR_CACHE_FILE, USE_SOLAR_CACHE,SOLAR_CACHE_DURATION)

# --- Home Assistant Sun Data Retrieval ---
def get_ha_sun_data():
    """Get sunrise/sunset data from Home Assistant sun.sun entity"""
    try:
        api_endpoint = f"{HA_URL}/api/states/sun.sun"
        response = requests.get(api_endpoint, headers=headers)
        response.raise_for_status()
        sun_data = response.json()

        attributes = sun_data.get("attributes", {})
        next_setting = attributes.get("next_setting")
        next_rising = attributes.get("next_rising")

        if next_setting:
            # Parse the ISO format datetime and convert to local timezone
            sunset_dt_utc = datetime.fromisoformat(next_setting.replace('Z', '+00:00'))
            # Convert to local timezone
            local_tz = ZoneInfo(time_zone)
            sunset_dt_local = sunset_dt_utc.astimezone(local_tz)
            sunset_time = sunset_dt_local.strftime("%H:%M:%S")
        else:
            sunset_time = None
            sunset_dt_local = None

        # Handle next_rising similarly if present
        if next_rising:
            sunrise_dt_utc = datetime.fromisoformat(next_rising.replace('Z', '+00:00'))
            sunrise_dt_local = sunrise_dt_utc.astimezone(local_tz)
            sunrise_time = sunrise_dt_local.strftime("%H:%M:%S")
        else:
            sunrise_time = None

        logger.info(f"Retrieved sun data from Home Assistant: sunset={sunset_time} (local time)")
        return {
            "sunset_time": sunset_time,
            "sunset_datetime": sunset_dt_local,
            "sunrise_time": sunrise_time,
            "next_rising": next_rising,
            "state": sun_data.get("state")
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Home Assistant sun data: {e}")
        return {"sunset_time": None, "sunset_datetime": None, "sunrise_time": None, "next_rising": None, "state": None}
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing Home Assistant sun data: {e}")
        return {"sunset_time": None, "sunset_datetime": None, "sunrise_time": None, "next_rising": None, "state": None}

sun_data = get_ha_sun_data()
sunset_time = sun_data["sunset_time"]

# --- Charge Rate Calculation ---
def calculate_charge_rate(deficit_kwh, window_start, window_end, current_time=None):
    """Calculate optimal charge rate based on remaining time in charging window"""
    if current_time is None:
        current_time = datetime.now()

    # Convert window times to today's date
    today = current_time.date()
    try:
        start_time = datetime.strptime(f"{today} {window_start}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{today} {window_end}", "%Y-%m-%d %H:%M")
    except ValueError as e:
        logger.error(f"Invalid time format in charging window: {e}")
        return 0

    # Adjust for next day if end time is earlier than start time
    if end_time < start_time:
        end_time += timedelta(days=1)

    # Adjust start time to next day if current time is past end time
    if current_time > end_time:
        start_time += timedelta(days=1)
        end_time += timedelta(days=1)

    # If current time is before start time, use full window
    if current_time < start_time:
        charging_end = end_time
    else:
        charging_end = end_time
        start_time = current_time

    # Calculate remaining hours (subtract 1 hour safety margin)
    remaining_hours = (charging_end - start_time).total_seconds() / 3600 - 1

    # If less than 1 hour remaining, use remaining time without safety margin
    if remaining_hours < 1:
        remaining_hours = (charging_end - start_time).total_seconds() / 3600

    # Calculate required charge rate in watts
    if remaining_hours <= 0:
        return 0

    required_watts = (deficit_kwh * 1000) / remaining_hours
    return max(round(required_watts), 0)



def force_charge_inverter(charging_power, fronius_host=None):
    """
    Performs the Modbus commands to force the inverter to charge.

    Args:
        charging_power (int): The desired charging power in Watts, e.g., 2000.
        fronius_host (str): Host IP address (uses FRONIUS_HOST if None)
    """
    host = fronius_host or FRONIUS_HOST

    # Apply maximum charge rate limit
    if charging_power > MAX_BATTERY_CHARGE_RATE:
        logger.warning(f"Requested charging power {charging_power}W exceeds maximum {MAX_BATTERY_CHARGE_RATE}W. Limiting to {MAX_BATTERY_CHARGE_RATE}W.")
        charging_power = MAX_BATTERY_CHARGE_RATE

    client = None  # Initialize client to None

    try:
        client = ModbusTcpClient(host, port=502)
        if not client.connect():
            logger.error("Failed to connect to the inverter.")
            return False

        # 1. Force charging mode
        register_40348 = 40348
        value_40348 = 2
        result_1 = client.write_register(register_40348, value_40348)
        if result_1.isError():
            logger.error(f"Error writing to register {register_40348}: {result_1}")
            return False

        logger.info(f"Set charging mode (register {register_40348}) to {value_40348}.")

        # 2. Determine and set charging power
        register_40355 = 40355

        if charging_power < 10:
            value_40355 = 55536
            logger.info("Charging power is low (< 10W). Setting minimum charging value.")
        else:
            scaled_power = -int(charging_power / 10)
            value_40355 = 65536 + scaled_power
            logger.info(f"Setting charging power to {charging_power}W. Scaled value: {scaled_power}.")

        result_2 = client.write_register(register_40355, value_40355)
        if result_2.isError():
            logger.error(f"Error writing to register {register_40355}: {result_2}")
            return False

        logger.info(f"Set charging power (register {register_40355}) to {value_40355}.")

        # 3. Set SOC limit
        register_40350 = 40350
        value_40350 = 9900
        result_3 = client.write_register(register_40350, value_40350)
        if result_3.isError():
            logger.error(f"Error writing to register {register_40350}: {result_3}")
            return False

        logger.info(f"Set SOC limit (register {register_40350}) to {value_40350} (99%).")

        logger.info("Inverter charging successfully initiated.")
        return True

    finally:
        if client:  # Check if the client object exists before closing
            client.close()

def read_battery_status(fronius_host=None):
    """Read current battery control mode and charge rate"""
    host = fronius_host or FRONIUS_HOST
    client = ModbusTcpClient(host, port=502, timeout=10)
    try:
        if not client.connect():
            logger.error("Failed to connect to Fronius inverter")
            return None, None

        # Read current control mode (register 40348)
        mode_result = client.read_holding_registers(40347, 1, unit=1)  # 40348-1 for 0-based
        if mode_result.isError():
            logger.error(f"Error reading control mode: {mode_result}")
            return None, None

        # Read current charge rate (register 40356)
        rate_result = client.read_holding_registers(40355, 1, unit=1)  # 40356-1 for 0-based
        if rate_result.isError():
            logger.error(f"Error reading charge rate: {rate_result}")
            return mode_result.registers[0], None

        control_mode = mode_result.registers[0]
        charge_rate = rate_result.registers[0]

        mode_names = {0: "External Control", 1: "Normal Mode", 2: "Disable", 3: "External Charge"}
        mode_name = mode_names.get(control_mode, f"Unknown ({control_mode})")

        logger.info(f"Current status - Mode: {mode_name}, Charge Rate: {charge_rate}W")
        return control_mode, charge_rate

    except Exception as e:
        logger.error(f"Error reading battery status: {e}")
        return None, None
    finally:
        client.close()

def reset_inverter_settings(fronius_host=None):
    """
    Resets the Modbus registers to return control to the inverter's
    automatic charging and discharging logic.
    """
    host = fronius_host or FRONIUS_HOST
    client = None

    try:
        client = ModbusTcpClient(host, port=502)
        if not client.connect():
            logger.error("Failed to connect to the inverter.")
            return False

        # 1. Reset charging mode to automatic (value 0)
        register_40348 = 40348
        value_40348 = 0
        result_1 = client.write_register(register_40348, value_40348)
        if result_1.isError():
            logger.error(f"Error writing to register {register_40348}: {result_1}")
            return False
        logger.info(f"Reset charging mode (register {register_40348}) to {value_40348}.")

        # 2. Reset input charging power rate
        register_40355 = 40355
        value_40355 = 10000
        result_2 = client.write_register(register_40355, value_40355)
        if result_2.isError():
            logger.error(f"Error writing to register {register_40355}: {result_2}")
            return False
        logger.info(f"Reset input charging power rate (register {register_40355}) to {value_40355}.")

        # 3. Reset minimum SOC to 5% (value 500)
        register_40350 = 40350
        value_40350 = 500
        result_3 = client.write_register(register_40350, value_40350)
        if result_3.isError():
            logger.error(f"Error writing to register {register_40350}: {result_3}")
            return False
        logger.info(f"Reset minimum SOC (register {register_40350}) to {value_40350} (5%).")

        # 4. Reset maximum discharge power rate
        register_40356 = 40356
        value_40356 = 10000
        result_4 = client.write_register(register_40356, value_40356)
        if result_4.isError():
            logger.error(f"Error writing to register {register_40356}: {result_4}")
            return False
        logger.info(f"Reset maximum discharge power rate (register {register_40356}) to {value_40356}.")

        logger.info("Inverter settings successfully reset to automatic mode.")
        return True

    except Exception as e:
        logger.error(f"Error in reset_inverter_settings: {e}")
        return False
    finally:
        if client:
            client.close()



# --- Initialize variables ---
total_deficit_kwh = 0
charge_rate = 0
battery_will_charge_overnight = False  # Will indicate if battery needs overnight charging

# --- Deficit Calculation ---
if "error" in solar_forecast_data:
    print(solar_forecast_data["error"])
else:
    # Validate battery efficiency to prevent division by zero
    if BATTERY_CHARGE_EFFICIENCY <= 0:
        print("Error: Battery charge efficiency must be greater than 0")
        exit(1)

    total_solar_kwh = solar_forecast_data["total_solar_kwh"]
    current_soc_percent = latest_soc if latest_soc is not None else 0.0
    current_soc_kwh = (current_soc_percent / 100.0) * BATTERY_SIZE_KWH
    usable_soc_percent = max(current_soc_percent - MINIMUM_SOC_PERCENT, 0.0)
    usable_soc_kwh = (usable_soc_percent / 100.0) * BATTERY_SIZE_KWH
    sunset_target_kwh = (MINIMUM_SOC_BY_SUNSET / 100.0) * BATTERY_SIZE_KWH
    sunset_deficit_kwh = max(sunset_target_kwh - current_soc_kwh, 0)

    # Include sunset target in total deficit
    total_deficit_kwh = predicted_power_need_kwh - (total_solar_kwh + usable_soc_kwh) + sunset_deficit_kwh

    # Adjust for battery efficiency
    total_deficit_kwh /= BATTERY_CHARGE_EFFICIENCY

    print(f"Forecasted Solar Production: {total_solar_kwh:.2f} kWh")
    print(f"Forecasted Power Need: {predicted_power_need_kwh:.2f} kWh")
    print(f"Current SOC: {current_soc_percent:.2f}% ({current_soc_kwh:.2f} kWh)")
    print(f"Usable SOC above minimum: {usable_soc_percent:.2f}% ({usable_soc_kwh:.2f} kWh)")
    print(f"Target SOC by sunset: {MINIMUM_SOC_BY_SUNSET:.2f}% ({sunset_target_kwh:.2f} kWh)")
    print(f"Next sunset time: {sunset_time}")
    print(f"Sun state: {sun_data['state']}")

    if sunset_deficit_kwh > 0:
        print(f"⚠️ Battery SOC is below sunset target. Need {sunset_deficit_kwh:.2f} kWh more.")

    if total_deficit_kwh > 0:
        battery_will_charge_overnight = True  # Battery needs overnight charging
        charge_rate = calculate_charge_rate(total_deficit_kwh, CHEAP_POWER_WINDOW[0], CHEAP_POWER_WINDOW[1])
        print(f"⚡ Total deficit (adjusted for efficiency): {total_deficit_kwh:.2f} kWh")
        print(f"🔋 Battery will need overnight charging")
        if charge_rate > 0:
            print(f"Recommended charge rate: {charge_rate} watts")
            print(f"Charging window: {CHEAP_POWER_WINDOW[0]} to {CHEAP_POWER_WINDOW[1]}")
        else:
            print("Outside charging window. Wait until next window begins.")
    else:
        battery_will_charge_overnight = False  # No overnight charging needed
        print("✅ Solar + current SOC is sufficient. No overnight charging needed.")


# --- Load previous charging state ---
def load_charging_state():
    """Load the last known charging state from file"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                return state.get('currently_charging', False)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load charging state: {e}")
    return False

def save_charging_state(charging):
    """Save the current charging state to file"""
    try:
        state = {'currently_charging': charging, 'timestamp': datetime.now().isoformat()}
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except IOError as e:
        logger.error(f"Could not save charging state: {e}")

# --- Decision Logic and Charge Control ---
currently_charging = load_charging_state()  # Load last known state
should_charge = False  # Determine if we should be charging

logger.info(f"Previous charging state: {'charging' if currently_charging else 'not charging'}")

if total_deficit_kwh > 0:
    current_time = datetime.now()
    charge_rate = calculate_charge_rate(total_deficit_kwh, CHEAP_POWER_WINDOW[0], CHEAP_POWER_WINDOW[1], current_time)
    print(f"⚡ Total deficit (adjusted for efficiency): {total_deficit_kwh:.2f} kWh")

    # Parse window times
    today = current_time.date()
    try:
        start_time = datetime.strptime(f"{today} {CHEAP_POWER_WINDOW[0]}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{today} {CHEAP_POWER_WINDOW[1]}", "%Y-%m-%d %H:%M")
    except ValueError as e:
        logger.error(f"Invalid time format in charging window: {e}")
        print("❌ Invalid charging window time format")
        should_charge = False

    if 'start_time' in locals():  # Only proceed if time parsing succeeded
        # Adjust for overnight window
        if end_time < start_time:
            end_time += timedelta(days=1)
        if current_time > end_time:
            start_time += timedelta(days=1)
            end_time += timedelta(days=1)

        # Check if we're in the charging window and should charge
        if start_time <= current_time <= end_time and charge_rate > 0:
            should_charge = True
            print(f"In charging window - Should charge at {charge_rate} watts")
        elif start_time <= current_time <= end_time:
            should_charge = False
            print("In charging window but target reached or insufficient time remaining")
        else:
            should_charge = False
            print(f"Outside charging window ({CHEAP_POWER_WINDOW[0]} to {CHEAP_POWER_WINDOW[1]})")
else:
    should_charge = False
    print("✅ Solar + current SOC is sufficient. No charging needed.")

# Only write to modbus if state needs to change
if should_charge and not currently_charging:
    # Start charging
    print("🔌 Starting battery charge from mains")
    if force_charge_inverter(charge_rate):
        currently_charging = True
        save_charging_state(True)
    else:
        print("❌ Failed to start charging")
        currently_charging = False
        save_charging_state(False)
elif not should_charge and currently_charging:
    # Stop charging
    print("🛑 Stopping battery charge")
    reset_inverter_settings()
    currently_charging = False
    save_charging_state(False)
elif should_charge and currently_charging:
    print("🔋 Continuing to charge (already charging)")
    # Update charge rate if it has changed significantly
    # Note: You might want to track previous charge rate and only update if changed
else:
    print("⏸️ No modbus action needed (charge state unchanged)")

# --- MQTT Setup ---
def setup_mqtt_client():
    # Create client with unique ID to avoid connection conflicts
    # Use the latest CallbackAPIVersion for paho-mqtt 2.x
    try:
        # Try new paho-mqtt 2.x syntax with latest version
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"solar_forecast_{int(time.time())}")
    except (AttributeError, TypeError):
        # Fallback to old syntax for paho-mqtt 1.x
        client = mqtt.Client(client_id=f"solar_forecast_{int(time.time())}")

    # Set up connection callback to verify success
    connected = False

    def on_connect(client, userdata, flags, rc):
        nonlocal connected
        if rc == 0:
            logger.info("Connected to MQTT broker")
            connected = True
        else:
            logger.error(f"Failed to connect to MQTT broker with code: {rc}")
            connected = False

    client.on_connect = on_connect

    try:
        # Use the mqtt_broker from config instead of mqtt_host
        broker = args.mqtt_broker.replace("mqtt://", "").replace("mqtts://", "")  # Strip protocol prefixes

        if args.mqtt_username and args.mqtt_password and args.mqtt_username.strip() and args.mqtt_password.strip():
            client.username_pw_set(args.mqtt_username.strip(), args.mqtt_password.strip())
            logger.info(f"MQTT credentials set for user: {args.mqtt_username.strip()}")
        else:
            logger.info("No MQTT credentials provided, connecting anonymously")

        logger.info(f"Attempting to connect to MQTT broker: {broker}:{args.mqtt_broker_port}")

        # Connect with timeout
        client.connect(broker, args.mqtt_broker_port, 60)
        client.loop_start()

        # Wait for connection with better timeout handling
        retry_count = 0
        max_retries = 10  # Increased retry count
        while not connected and retry_count < max_retries:
            time.sleep(0.5)  # Shorter sleep intervals
            retry_count += 1

        if not connected:
            logger.error(f"Failed to connect to MQTT broker after {max_retries} retries")
            try:
                client.loop_stop()
                client.disconnect()
            except:
                pass
            return None

        logger.info("Successfully connected to MQTT broker")
        return client

    except Exception as e:
        logger.error(f"Failed to connect to MQTT broker: {e}")
        try:
            client.loop_stop()
            client.disconnect()
        except:
            pass
        return None

def publish_mqtt_update(mqtt_client, topic, payload):
    if not mqtt_client:
        logger.error("MQTT client not initialized - cannot publish update")
        return False

    # Check connection state - is_connected() may not be available in all versions
    try:
        if not mqtt_client.is_connected():
            logger.error("MQTT client not connected - cannot publish update")
            return False
    except AttributeError:
        # Fallback for older paho-mqtt versions without is_connected()
        logger.warning("Cannot check MQTT connection state, attempting publish anyway")

    try:
        if not isinstance(payload, str):
            payload = json.dumps(payload, default=str)  # Handle datetime serialization

        full_topic = f"{args.mqtt_topic_prefix}/{topic}"
        result = mqtt_client.publish(full_topic, payload, qos=1, retain=True)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Failed to publish to MQTT: {mqtt.error_string(result.rc)}")
            return False

        # Wait for the message to be published (with timeout)
        try:
            result.wait_for_publish(timeout=5.0)
            logger.info(f"Successfully published to MQTT topic: {full_topic}")
        except Exception as e:
            logger.warning(f"Message published but couldn't confirm delivery: {e}")

        return True

    except Exception as e:
        logger.error(f"Failed to publish to MQTT: {e}")
        return False

# Initialize MQTT client once at the start
mqtt_client = setup_mqtt_client()


# Prepare forecast data for MQTT publishing
forecast_data = {
    "timestamp": datetime.now().isoformat(),
    "solar_forecast": solar_forecast_data,
    "predicted_power_need_kwh": predicted_power_need_kwh,
    "total_deficit_kwh": total_deficit_kwh,
    "current_soc": current_soc_percent,
    "sun_data": {
        "sunset_time": sunset_time,
        "sunrise_time": sun_data["sunrise_time"],
        "next_rising": sun_data["next_rising"],
        "state": sun_data["state"]
    },
    "battery_will_charge_overnight": battery_will_charge_overnight,  # Will need overnight charging
    "currently_charging": currently_charging,  # Actually charging right now
    "required_charge_rate": charge_rate,
    "charging_window": {
        "start": CHEAP_POWER_WINDOW[0],
        "end": CHEAP_POWER_WINDOW[1]
    }
}

if mqtt_client:
    # Publish main status data
    success = publish_mqtt_update(mqtt_client, "status", forecast_data)
    if not success:
        logger.error("Failed to publish forecast data to MQTT")

    # Publish individual sensor values for easier Home Assistant integration
    individual_topics = {
        "solar_forecast_kwh": solar_forecast_data.get("total_solar_kwh", 0),
        "predicted_power_need_kwh": predicted_power_need_kwh,
        "current_soc_percent": current_soc_percent,
        "battery_will_charge_overnight": battery_will_charge_overnight,  # Will need overnight charging
        "currently_charging": currently_charging,  # Actually charging right now
        "required_charge_rate": charge_rate,
        "total_deficit_kwh": total_deficit_kwh
    }

    for topic, value in individual_topics.items():
        # Convert boolean values to ON/OFF for binary sensors
        if isinstance(value, bool):
            mqtt_value = "ON" if value else "OFF"
        else:
            mqtt_value = str(value)
        publish_mqtt_update(mqtt_client, topic, mqtt_value)

# Cleanup at the end
if mqtt_client:
    try:
        logger.info("Disconnecting from MQTT broker")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        # Wait a moment for clean disconnect
        time.sleep(0.5)
    except Exception as e:
        logger.error(f"Error during MQTT cleanup: {e}")

# Final memory cleanup
if 'forecast_data' in locals():
    del forecast_data
del df_forecast, model, X, y


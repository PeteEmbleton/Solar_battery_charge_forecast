#!/usr/bin/env python3

import json
import time
import argparse
import logging
import os
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_mqtt_client(broker, port, username=None, password=None):
    """Setup and connect MQTT client"""
    try:
        # Try new paho-mqtt 2.x syntax with latest version
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"solar_discovery_{int(time.time())}")
    except (AttributeError, TypeError):
        # Fallback to old syntax for paho-mqtt 1.x
        client = mqtt.Client(client_id=f"solar_discovery_{int(time.time())}")

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
        # Strip protocol prefixes
        broker_clean = broker.replace("mqtt://", "").replace("mqtts://", "")

        if username and password and username.strip() and password.strip():
            client.username_pw_set(username.strip(), password.strip())
            logger.info(f"MQTT credentials set for user: {username.strip()}")
        else:
            logger.info("No MQTT credentials provided, connecting anonymously")

        logger.info(f"Attempting to connect to MQTT broker: {broker_clean}:{port}")

        # Connect with timeout
        client.connect(broker_clean, port, 60)
        client.loop_start()

        # Wait for connection with timeout
        retry_count = 0
        max_retries = 10
        while not connected and retry_count < max_retries:
            time.sleep(0.5)
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

def publish_mqtt_discovery(mqtt_client, topic_prefix="solar_forecast"):
    """Publish MQTT discovery messages to auto-create sensors in Home Assistant"""
    if not mqtt_client:
        logger.warning("MQTT client not available - skipping discovery")
        return False

    logger.info(f"Starting MQTT discovery publishing with topic prefix: {topic_prefix}")

    device_info = {
        "identifiers": ["solar_forecast_battery_control"],
        "name": "Solar Forecast and Battery Control",
        "manufacturer": "Custom Addon",
        "model": "MQTT Solar Forecaster",
        "sw_version": "1.0"
    }

    sensors = [
        {
            "name": "Solar Forecast Required Charge Rate",
            "state_topic": f"{topic_prefix}/required_charge_rate",
            "unit_of_measurement": "W",
            "unique_id": "solar_forecast_required_charge_rate",
            "device_class": "power",
            "icon": "mdi:battery-charging"
        },
        {
            "name": "Solar Forecast Battery SOC",
            "state_topic": f"{topic_prefix}/current_soc_percent",
            "unit_of_measurement": "%",
            "unique_id": "solar_forecast_battery_soc",
            "device_class": "battery",
            "icon": "mdi:battery"
        },
        {
            "name": "Solar Forecast Total Deficit",
            "state_topic": f"{topic_prefix}/total_deficit_kwh",
            "unit_of_measurement": "kWh",
            "unique_id": "solar_forecast_total_deficit",
            "device_class": "energy",
            "icon": "mdi:battery-minus"
        },
        {
            "name": "Solar Forecast Predicted Power Need",
            "state_topic": f"{topic_prefix}/predicted_power_need_kwh",
            "unit_of_measurement": "kWh",
            "unique_id": "solar_forecast_predicted_power_need",
            "device_class": "energy",
            "icon": "mdi:home-lightning-bolt"
        },
        {
            "name": "Solar Forecast Battery Will Charge Overnight",
            "state_topic": f"{topic_prefix}/battery_will_charge_overnight",
            "unique_id": "solar_forecast_battery_will_charge_overnight",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "battery_charging",
            "icon": "mdi:battery-clock"
        },
        {
            "name": "Solar Forecast Currently Charging",
            "state_topic": f"{topic_prefix}/currently_charging",
            "unique_id": "solar_forecast_currently_charging",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "battery_charging",
            "icon": "mdi:battery-charging-wireless"
        },
        {
            "name": "Solar Forecast Solar Generation",
            "state_topic": f"{topic_prefix}/solar_forecast_kwh",
            "unit_of_measurement": "kWh",
            "unique_id": "solar_forecast_solar_kwh",
            "device_class": "energy",
            "icon": "mdi:solar-power"
        },
        {
            "name": "Solar Forecast Sunset Time",
            "state_topic": f"{topic_prefix}/status",
            "value_template": "{{ value_json.sun_data.sunset_time }}",
            "unique_id": "solar_forecast_sunset_time",
            "icon": "mdi:weather-sunset"
        },
        {
            "name": "Solar Forecast Sunrise Time",
            "state_topic": f"{topic_prefix}/status",
            "value_template": "{{ value_json.sun_data.sunrise_time }}",
            "unique_id": "solar_forecast_sunrise_time",
            "icon": "mdi:weather-sunrise"
        },
        {
            "name": "Solar Forecast Sun State",
            "state_topic": f"{topic_prefix}/status",
            "value_template": "{{ value_json.sun_data.state }}",
            "unique_id": "solar_forecast_sun_state",
            "icon": "mdi:weather-sunny"
        }
    ]

    success_count = 0
    # Publish discovery messages
    for sensor in sensors:
        # Use binary_sensor for boolean values
        if 'payload_on' in sensor:
            discovery_topic = f"homeassistant/binary_sensor/{sensor['unique_id']}/config"
        else:
            discovery_topic = f"homeassistant/sensor/{sensor['unique_id']}/config"
        payload = dict(sensor)
        payload["device"] = device_info

        try:
            result = mqtt_client.publish(discovery_topic, json.dumps(payload), retain=True, qos=1)
            if result.rc == 0:
                logger.info(f"Published discovery for: {sensor['name']}")
                success_count += 1
            else:
                logger.error(f"Failed to publish discovery for: {sensor['name']}")
        except Exception as e:
            logger.error(f"Error publishing discovery for {sensor['name']}: {e}")

    logger.info(f"Successfully published {success_count}/{len(sensors)} discovery messages")
    return success_count == len(sensors)

def main():
    parser = argparse.ArgumentParser(description="Publish MQTT Discovery for Solar Forecast sensors")
    parser.add_argument("--mqtt_broker", default="mqtt://core-mosquitto", help="MQTT broker URL")
    parser.add_argument("--mqtt_broker_port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt_topic_prefix", default="solar_forecast", help="MQTT topic prefix")
    parser.add_argument("--mqtt_username", default="", help="MQTT username")
    parser.add_argument("--mqtt_password", default="", help="MQTT password")
    parser.add_argument("--retry_attempts", type=int, default=3, help="Number of retry attempts")
    parser.add_argument("--retry_delay", type=int, default=5, help="Delay between retries in seconds")

    args = parser.parse_args()

    logger.info("Starting MQTT Discovery for Solar Forecast sensors")

    # Retry logic for startup scenarios where MQTT might not be ready yet
    for attempt in range(args.retry_attempts):
        logger.info(f"Connection attempt {attempt + 1}/{args.retry_attempts}")

        mqtt_client = setup_mqtt_client(
            args.mqtt_broker,
            args.mqtt_broker_port,
            args.mqtt_username if args.mqtt_username else None,
            args.mqtt_password if args.mqtt_password else None
        )

        if mqtt_client:
            success = publish_mqtt_discovery(mqtt_client, args.mqtt_topic_prefix)

            # Cleanup
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
                time.sleep(0.5)  # Allow clean disconnect
            except Exception as e:
                logger.error(f"Error during MQTT cleanup: {e}")

            if success:
                logger.info("MQTT Discovery completed successfully")
                return 0
            else:
                logger.warning("Some discovery messages failed to publish")

        if attempt < args.retry_attempts - 1:
            logger.info(f"Retrying in {args.retry_delay} seconds...")
            time.sleep(args.retry_delay)

    logger.error("Failed to publish MQTT discovery after all attempts")
    return 1

if __name__ == "__main__":
    exit(main())

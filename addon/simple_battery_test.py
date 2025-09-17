#!/usr/bin/env python3

import sys
import os
import logging
import time
import json
import paho.mqtt.client as mqtt
try:
    from pymodbus.client.sync import ModbusTcpClient
except ImportError:
    from pymodbus.client import ModbusTcpClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load config from Home Assistant addon options
def load_addon_config():
    """Load configuration from Home Assistant addon options"""
    config_file = '/data/options.json'
    try:
        with open(config_file, 'r') as f:
            addon_config = json.load(f)

        config_data = {
            'fronius_host': addon_config.get('fronius_host'),
            'mqtt_broker': addon_config.get('mqtt_broker'),
            'mqtt_broker_port': addon_config.get('mqtt_broker_port', 1883),
            'mqtt_topic_prefix': addon_config.get('mqtt_topic_prefix', 'battery_test'),
            'mqtt_username': addon_config.get('mqtt_username'),
            'mqtt_password': addon_config.get('mqtt_password'),
            'max_battery_charge_rate': addon_config.get('max_battery_charge_rate', 5000)
        }
        logger.info(f"Loaded Home Assistant addon config - Fronius host: {config_data['fronius_host']}")
        return config_data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load addon config: {e}")
        # Fallback to environment variables for testing
        logger.info("Using environment variables as fallback")
        return {
            'fronius_host': os.environ.get('FRONIUS_HOST'),
            'mqtt_broker': os.environ.get('MQTT_BROKER'),
            'mqtt_broker_port': int(os.environ.get('MQTT_BROKER_PORT', 1883)),
            'mqtt_topic_prefix': os.environ.get('MQTT_TOPIC_PREFIX', 'battery_test'),
            'mqtt_username': os.environ.get('MQTT_USERNAME'),
            'mqtt_password': os.environ.get('MQTT_PASSWORD'),
            'max_battery_charge_rate': int(os.environ.get('MAX_BATTERY_CHARGE_RATE', 5000))
        }

config = load_addon_config()

# FORCE CHARGE FUNCTION
def force_charge_inverter(charging_power, fronius_host=None):
    """
    Performs the Modbus commands to force the inverter to charge.

    Args:
        charging_power (int): The desired charging power in Watts, e.g., 2000.
        fronius_host (str): Host IP address (uses config if None)
    """
    host = fronius_host or config['fronius_host']

    # Apply maximum charge rate limit
    max_charge_rate = config.get('max_battery_charge_rate', 5000)
    if charging_power > max_charge_rate:
        logger.warning(f"Requested charging power {charging_power}W exceeds maximum {max_charge_rate}W. Limiting to {max_charge_rate}W.")
        charging_power = max_charge_rate

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
    host = fronius_host or config['fronius_host']
    client = ModbusTcpClient(host, port=502, timeout=10)
    try:
        if not client.connect():
            logger.error("Failed to connect to Fronius inverter")
            return None, None

        # First, check SunSpec model type
        try:
            sunspec_result = client.read_holding_registers(39999, count=2)  # 40000-1 for 0-based, read 2 registers
            if not sunspec_result.isError():
                logger.info(f"SunSpec header: {sunspec_result.registers}")
        except:
            pass

        # Try both INT+SF and FLOAT model registers
        control_mode = None
        charge_rate = None

        # Try INT+SF model first (original registers)
        try:
            mode_result = client.read_holding_registers(40347)  # 40348-1 for 0-based
            if not mode_result.isError():
                control_mode = mode_result.registers[0]
                logger.info(f"INT+SF Model - Control Mode: {control_mode}")
        except Exception as e:
            logger.info(f"INT+SF mode read failed: {e}")

        try:
            rate_result = client.read_holding_registers(40355)  # 40356-1 for 0-based
            if not rate_result.isError():
                charge_rate = rate_result.registers[0]
                logger.info(f"INT+SF Model - Charge Rate: {charge_rate}")
        except Exception as e:
            logger.info(f"INT+SF rate read failed: {e}")

        # If INT+SF didn't work or gave weird values, try FLOAT model
        if control_mode is None or control_mode > 10:  # Sanity check
            try:
                mode_result = client.read_holding_registers(40357)  # 40358-1 for 0-based (FLOAT model)
                if not mode_result.isError():
                    control_mode = mode_result.registers[0]
                    logger.info(f"FLOAT Model - Control Mode: {control_mode}")
            except Exception as e:
                logger.info(f"FLOAT mode read failed: {e}")

        if charge_rate is None or charge_rate > 50000:  # Sanity check
            try:
                rate_result = client.read_holding_registers(40365)  # 40366-1 for 0-based (FLOAT model)
                if not rate_result.isError():
                    charge_rate = rate_result.registers[0]
                    logger.info(f"FLOAT Model - Charge Rate: {charge_rate}")
            except Exception as e:
                logger.info(f"FLOAT rate read failed: {e}")

        if control_mode is None:
            logger.error("Could not read control mode from either model")
            return None, None

        mode_names = {0: "External Control", 1: "Normal Mode", 2: "Disable", 3: "External Charge"}
        mode_name = mode_names.get(control_mode, f"Unknown ({control_mode})")

        logger.info(f"Final status - Mode: {mode_name}, Charge Rate: {charge_rate}W")
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
    host = fronius_host or config['fronius_host']
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

def setup_mqtt():
    """Setup MQTT client using config"""
    if not config['mqtt_broker']:
        return None

    try:
        client = mqtt.Client(client_id=f"battery_test_{int(time.time())}")

        if config['mqtt_username'] and config['mqtt_password']:
            client.username_pw_set(config['mqtt_username'], config['mqtt_password'])

        broker_clean = config['mqtt_broker'].replace("mqtt://", "").replace("mqtts://", "")
        client.connect(broker_clean, config['mqtt_broker_port'], 60)
        client.loop_start()
        logger.info(f"Connected to MQTT broker at {broker_clean}:{config['mqtt_broker_port']}")
        return client
    except Exception as e:
        logger.warning(f"MQTT connection failed: {e}")
        return None

def publish_status(mqtt_client, status, message):
    """Publish status to MQTT"""
    if not mqtt_client:
        return

    status_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "message": message,
        "fronius_host": config['fronius_host']
    }

    try:
        topic = f"{config['mqtt_topic_prefix']}/status"
        mqtt_client.publish(topic, json.dumps(status_data), retain=True, qos=1)
        logger.info(f"Published status to MQTT: {status}")
    except Exception as e:
        logger.error(f"Failed to publish to MQTT: {e}")

def main():
    # Get action from command line
    if len(sys.argv) != 2 or sys.argv[1] not in ['start', 'stop', 'status']:
        logger.error("Usage: simple_battery_test.py {start|stop|status}")
        sys.exit(1)

    action = sys.argv[1]

    if not config['fronius_host']:
        logger.error("FRONIUS_HOST not configured")
        sys.exit(1)

    mqtt_client = setup_mqtt()

    try:
        if action == "start":
            max_charge_rate = config.get('max_battery_charge_rate', 5000)
            test_charge_rate = max_charge_rate // 2  # Use half max rate for testing
            logger.info(f"🔋 Starting forced battery charge at {test_charge_rate}W (50% of max {max_charge_rate}W) using new force charge method")
            publish_status(mqtt_client, "starting", f"Starting forced battery charge at {test_charge_rate}W (50% of max)")

            # Use EXACT PRODUCTION functions
            mode, rate = read_battery_status(config['fronius_host'])
            if mode is None:
                logger.error("❌ Failed to read battery status")
                publish_status(mqtt_client, "error", "Failed to read battery status")
                return False

            # Check for force charge mode - could be mode 2 or other values depending on inverter
            if mode in [2, 100]:  # Mode 100 seems to be force charge on your inverter
                logger.warning("⚠️ Battery already in Force Charge mode")
                publish_status(mqtt_client, "already_charging", f"Battery already charging at {rate}W")
                return True

            # Use half the configured max charge rate for safe testing
            max_charge_rate = config.get('max_battery_charge_rate', 5000)
            test_charge_rate = max_charge_rate // 2  # Use integer division for clean watts
            success = force_charge_inverter(test_charge_rate, config['fronius_host'])
            if success:
                time.sleep(2)
                verify_mode, verify_rate = read_battery_status(config['fronius_host'])
                if verify_mode in [2, 100]:  # Accept both possible force charge modes
                    logger.info(f"✅ Test charge started successfully at {verify_rate}W")
                    publish_status(mqtt_client, "charging", f"Battery charging at {verify_rate}W")
                    return True

            logger.error("❌ Failed to start test charge")
            publish_status(mqtt_client, "error", "Failed to start test charge")
            return False

        elif action == "stop":
            logger.info("🛑 Resetting inverter to automatic mode using new reset method")
            publish_status(mqtt_client, "stopping", "Resetting inverter to automatic mode")

            mode, rate = read_battery_status(config['fronius_host'])
            if mode is None:
                logger.error("❌ Failed to read battery status")
                publish_status(mqtt_client, "error", "Failed to read battery status")
                return False

            # Check for automatic mode - could be mode 0 or other values
            if mode in [0, 1] or (mode == 100 and rate == 10000):  # Mode 100 with rate 10000 seems to be automatic
                logger.info("✅ Battery already in Automatic Mode")
                publish_status(mqtt_client, "stopped", "Battery already in Automatic Mode")
                return True

            success = reset_inverter_settings(config['fronius_host'])
            if success:
                time.sleep(2)
                verify_mode, verify_rate = read_battery_status(config['fronius_host'])
                if verify_mode in [0, 1] or (verify_mode == 100 and verify_rate == 10000):
                    logger.info("✅ Test charge stopped, returned to Automatic Mode")
                    publish_status(mqtt_client, "stopped", "Battery returned to Automatic Mode")
                    return True

            logger.error("❌ Failed to stop test charge")
            publish_status(mqtt_client, "error", "Failed to stop test charge")
            return False

        elif action == "status":
            logger.info("📊 Checking battery status using updated status reading")
            publish_status(mqtt_client, "checking", "Checking battery status")

            mode, rate = read_battery_status(config['fronius_host'])
            if mode is not None:
                mode_names = {0: "Automatic Mode", 1: "Normal Mode", 2: "Force Charge Mode", 100: "Force Charge Mode"}
                mode_name = mode_names.get(mode, f"Unknown Mode ({mode})")
                logger.info(f"📊 Battery Status: {mode_name}, Rate: {rate}W")
                publish_status(mqtt_client, "status", f"Mode: {mode_name}, Rate: {rate}W")
                return True

            logger.error("❌ Failed to read battery status")
            publish_status(mqtt_client, "error", "Failed to read battery status")
            return False

    finally:
        if mqtt_client:
            time.sleep(1)  # Give MQTT time to publish
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except:
                pass

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
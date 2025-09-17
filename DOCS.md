# Solar Forecast and Battery Control for Fronius Inverters

This Home Assistant add-on provides intelligent solar forecasting and automated battery charging control specifically designed for **Fronius inverters** with Modbus TCP capability.

## 🎯 Overview

The add-on learns from your energy usage patterns and weather forecasts to automatically charge your battery from the grid during cheap power periods, ensuring you have sufficient stored energy when solar production is low.

## ⚙️ How It Works

1. **Analyzes Historical Data** - Reviews your Home Assistant sensor history to understand power consumption patterns
2. **Forecasts Solar Production** - Uses Open-Meteo weather API to predict tomorrow's solar generation
3. **Predicts Power Needs** - Machine learning model predicts tomorrow's energy consumption
4. **Calculates Energy Deficit** - Determines if solar + current battery will meet tomorrow's needs
5. **Controls Fronius Inverter** - Automatically charges battery via Modbus TCP during configured cheap power windows
6. **Creates HA Sensors** - Auto-discovers and creates sensors in Home Assistant for monitoring and automation

## 🔌 Fronius Integration

- **Modbus TCP Control** - Direct communication with Fronius inverters
- **Charging Modes** - Switches between Normal Mode and External Charging
- **Rate Control** - Sets optimal charging rate based on remaining time in cheap power window
- **State Persistence** - Tracks charging state across add-on restarts to minimize unnecessary Modbus commands

## Configuration

### 🔧 Required Parameters:

#### System Configuration:

- `system_size_kw`: Your solar system size in kW
- `battery_size_kwh`: Your battery capacity in kWh
- `minimum_soc_percent`: Minimum state of charge percentage to maintain
- `minimum_soc_by_sunset`: Target SOC percentage by sunset

#### Power Window:

- `cheap_power_window_start`: Start time for cheap power (e.g., "23:30")
- `cheap_power_window_end`: End time for cheap power (e.g., "05:30")

#### Fronius Inverter:

- `fronius_host`: IP address of your Fronius inverter (e.g., "192.168.1.100")

### Optional Parameters:

- `ha_url`: Home Assistant URL (default: "http://supervisor/core")
- `cache_forecast`: Enable/disable forecast caching (default: true)
- `cache_duration`: Cache duration in minutes (default: 120)
- `battery_charge_efficiency`: Battery charge efficiency % (default: 95)
- `ha_days_to_retrieve`: Days of HA history to analyze (default: 30)

### Sensor Configuration:

- `HA_battery_charge_rate_sensor`: Battery charge rate sensor entity
- `HA_battery_SOC_sensor`: Battery state of charge sensor entity
- `HA_power_usage_sensor`: Power consumption sensor entity

### Battery Safety Configuration:

- `max_battery_charge_rate`: Maximum battery charging power in watts (default: 5000)
  - Sets the absolute maximum charging power that will never be exceeded
  - Main forecasting algorithm respects this limit
  - Test scripts use 50% of this value for safe testing

### MQTT Configuration:

- `mqtt_topic_prefix`: Topic prefix for MQTT messages (default: "solar_forecast")
- `mqtt_broker`: MQTT broker address (default: "mqtt://core-mosquitto")
- `mqtt_broker_port`: MQTT broker port (default: 1883)
- `mqtt_username`: MQTT username (optional)
- `mqtt_password`: MQTT password (optional)

## 📝 Example Configuration

```json
{
  "system_size_kw": 6.6,
  "battery_size_kwh": 19.7,
  "minimum_soc_percent": 20.0,
  "minimum_soc_by_sunset": 40.0,
  "cheap_power_window_start": "23:30",
  "cheap_power_window_end": "05:30",
  "fronius_host": "192.168.1.100",
  "max_battery_charge_rate": 5000,
  "cache_forecast": true,
  "battery_charge_efficiency": 95,
  "mqtt_broker": "mqtt://core-mosquitto",
  "mqtt_topic_prefix": "solar_forecast"
}
```

**Key Points:**

- `max_battery_charge_rate`: Set this to your battery's safe maximum charging power
- `fronius_host`: Replace with your actual Fronius inverter IP address
- Test charging will use 2500W (50% of the 5000W maximum in this example)

## 📡 MQTT Integration

### 🔄 Auto-Discovery

The add-on automatically creates Home Assistant sensors on startup using MQTT Discovery. **No manual sensor configuration required!**

**Device Created:** "Solar Forecast and Battery Control"
**Sensors Auto-Created:**

- Solar Forecast Required Charge Rate (W) - Power sensor with charging icon
- Solar Forecast Battery SOC (%) - Battery sensor
- Solar Forecast Total Deficit (kWh) - Energy sensor showing shortfall
- Solar Forecast Predicted Power Need (kWh) - Energy sensor for consumption
- Solar Forecast Battery Will Charge Overnight - Binary sensor (ON/OFF)
- Solar Forecast Currently Charging - Binary sensor (ON/OFF)
- Solar Forecast Solar Generation (kWh) - Energy sensor with solar icon
- Solar Forecast Sunset Time - Time display
- Solar Forecast Sunrise Time - Time display
- Solar Forecast Sun State - Current sun state (above/below horizon)

### MQTT Topics Published

#### Individual Sensor Topics:

- `solar_forecast/solar_forecast_kwh`: Tomorrow's predicted solar generation
- `solar_forecast/predicted_power_need_kwh`: Tomorrow's predicted power consumption
- `solar_forecast/total_deficit_kwh`: Energy shortfall requiring charging
- `solar_forecast/current_soc_percent`: Current battery state of charge
- `solar_forecast/battery_will_charge_overnight`: Will battery need overnight charging (ON/OFF)
- `solar_forecast/currently_charging`: Is battery actively charging now (ON/OFF)
- `solar_forecast/required_charge_rate`: Required charge rate in watts

#### Main Status Topic:

- `solar_forecast/status`: Complete status payload including:
  - Solar forecast details with hourly radiation data
  - Sun data (sunset/sunrise times, current state)
  - Charging window configuration
  - Battery status and predictions
  - Timestamp

## 🏠 Integration with Home Assistant

### Automatic Setup

**No manual configuration needed!** The add-on uses MQTT Discovery to automatically create all sensors when the container starts.

### Using the Sensors

Once running, you'll find all sensors under the **"Solar Forecast and Battery Control"** device in Home Assistant:

**Navigation:** Settings → Devices & Services → MQTT → Solar Forecast and Battery Control

### Example Automations

```yaml
# Get notified when battery will charge tonight
automation:
  - alias: "Battery Charging Tonight Notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.solar_forecast_battery_will_charge_overnight
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Battery Charging Tonight"
          message: "Deficit: {{ states('sensor.solar_forecast_total_deficit') }} kWh"

  # Monitor when charging actually starts
  - alias: "Battery Charging Started"
    trigger:
      - platform: state
        entity_id: binary_sensor.solar_forecast_currently_charging
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "🔋 Battery Charging Started"
          message: "Rate: {{ states('sensor.solar_forecast_required_charge_rate') }}W"
```

### Dashboard Cards

```yaml
# Energy card showing forecast vs actual
type: energy-date-selection
# Add the solar forecast sensor to compare predictions

# Simple entities card
type: entities
entities:
  - entity: sensor.solar_forecast_solar_generation
    name: "Tomorrow's Solar"
  - entity: sensor.solar_forecast_predicted_power_need
    name: "Predicted Usage"
  - entity: sensor.solar_forecast_total_deficit
    name: "Energy Deficit"
  - entity: binary_sensor.solar_forecast_battery_will_charge_overnight
    name: "Will Charge Tonight"
```

## 🔧 Fronius Setup Requirements

### Modbus TCP Configuration

1. **Enable Modbus TCP** on your Fronius inverter
2. **Set IP address** - Note your inverter's IP address
3. **Default port** - Usually 502 (standard Modbus port)
4. **Unit ID** - Typically 1 for Fronius inverters

### Required Fronius Registers

The add-on uses these Modbus registers for force charging:

- **40348** - Battery control mode (0=Automatic, 2=Force charge)
- **40355** - Input charging power rate (scaled value)
- **40350** - Minimum SOC limit (scaled percentage)
- **40356** - Maximum discharge power rate (for reset operations)

### Supported Fronius Models

Tested with Fronius inverters that support battery management. Most modern Fronius inverters with battery capability should work.

## 🧪 Battery Test Controls

The add-on includes test scripts to safely test your Fronius battery charging functionality from Home Assistant.

### Test Features

- **Safe test charging** - Uses 50% of configured `max_battery_charge_rate` for testing
- **Configurable power** - Test rate automatically adjusts based on your maximum setting
- **MQTT status updates** - Real-time feedback in Home Assistant
- **Automatic safety limits** - Prevents excessive charge rates
- **Status monitoring** - Check current battery control mode

**Example:** If `max_battery_charge_rate` is set to 6000W, test charging will use 3000W.

### Setting Up Test Switches

Add these to your Home Assistant configuration:

```yaml
# configuration.yaml
shell_command:
  battery_test_start: >
    CONTAINER=$(docker ps --filter 'name=solar_forecast_battery' --format '{{.Names}}' | head -1) &&
    [ ! -z "$CONTAINER" ] &&
    docker exec "$CONTAINER" /app/battery_test.sh start ||
    echo "Container not found"
  battery_test_stop: >
    CONTAINER=$(docker ps --filter 'name=solar_forecast_battery' --format '{{.Names}}' | head -1) &&
    [ ! -z "$CONTAINER" ] &&
    docker exec "$CONTAINER" /app/battery_test.sh stop ||
    echo "Container not found"
  battery_test_status: >
    CONTAINER=$(docker ps --filter 'name=solar_forecast_battery' --format '{{.Names}}' | head -1) &&
    [ ! -z "$CONTAINER" ] &&
    docker exec "$CONTAINER" /app/battery_test.sh status ||
    echo "Container not found"

# Create switches for easy testing
switch:
  - platform: template
    switches:
      battery_test_charge:
        friendly_name: "Battery Test Charge"
        value_template: "{{ state_attr('sensor.solar_forecast_battery_test_status', 'status') == 'charging' }}"
        turn_on:
          service: shell_command.battery_test_start
        turn_off:
          service: shell_command.battery_test_stop
        icon_template: >-
          {% if state_attr('sensor.solar_forecast_battery_test_status', 'status') == 'charging' %}
            mdi:battery-charging
          {% else %}
            mdi:battery
          {% endif %}

# Button for status check
button:
  - platform: template
    name: "Check Battery Status"
    press:
      service: shell_command.battery_test_status
    icon: mdi:battery-check
```

### Test Status Sensor

The test scripts publish status to MQTT. Add this sensor to monitor test status:

```yaml
# configuration.yaml
mqtt:
  sensor:
    - name: "Solar Forecast Battery Test Status"
      state_topic: "solar_forecast/status"
      value_template: "{{ value_json.status }}"
      json_attributes_topic: "solar_forecast/status"
      icon: mdi:battery-check
```

### Usage Instructions

1. **Start Test**: Use the "Battery Test Charge" switch to start a 100W trickle charge
2. **Monitor**: Watch the status sensor and check your Fronius monitoring
3. **Stop Test**: Turn off the switch to return battery to normal mode
4. **Status Check**: Use the "Check Battery Status" button anytime

### Safety Notes

- **Low power only** - Test charge is limited to 100W for safety
- **Manual stop required** - Always stop the test charge manually
- **Monitor closely** - Watch your battery and inverter during testing
- **Normal operation** - Test won't interfere with regular add-on operation

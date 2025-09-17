#!/usr/bin/with-contenv bashio

# ==============================================================================
# Battery Test Control Script for Home Assistant
# Can be called from HA switches/buttons to test Fronius battery charging
# ==============================================================================

set -e

ACTION="$1"
if [ -z "$ACTION" ]; then
    bashio::log.error "Usage: $0 {start|stop|status}"
    exit 1
fi

# Get configuration values from add-on config
HA_URL=$(bashio::config 'ha_url')
HA_TOKEN=$(bashio::config 'ha_token')
SYSTEM_SIZE_KW=$(bashio::config 'system_size_kw')
BATTERY_SIZE_KWH=$(bashio::config 'battery_size_kwh')
MINIMUM_SOC_PERCENT=$(bashio::config 'minimum_soc_percent')
MINIMUM_SOC_BY_SUNSET=$(bashio::config 'minimum_soc_by_sunset')
CHEAP_POWER_WINDOW_START=$(bashio::config 'cheap_power_window_start')
CHEAP_POWER_WINDOW_END=$(bashio::config 'cheap_power_window_end')
FRONIUS_HOST=$(bashio::config 'fronius_host')
CACHE_FORECAST=$(bashio::config 'cache_forecast')
CACHE_DURATION=$(bashio::config 'cache_duration')
BATTERY_CHARGE_EFFICIENCY=$(bashio::config 'battery_charge_efficiency')
HA_DAYS_TO_RETRIEVE=$(bashio::config 'ha_days_to_retrieve')
HA_BATTERY_CHARGE_RATE_SENSOR=$(bashio::config 'HA_battery_charge_rate_sensor')
HA_BATTERY_SOC_SENSOR=$(bashio::config 'HA_battery_SOC_sensor')
HA_POWER_USAGE_SENSOR=$(bashio::config 'HA_power_usage_sensor')
MQTT_BROKER=$(bashio::config 'mqtt_broker')
MQTT_BROKER_PORT=$(bashio::config 'mqtt_broker_port')
MQTT_TOPIC_PREFIX=$(bashio::config 'mqtt_topic_prefix')
MQTT_USERNAME=$(bashio::config 'mqtt_username')
MQTT_PASSWORD=$(bashio::config 'mqtt_password')
MAX_BATTERY_CHARGE_RATE=$(bashio::config 'max_battery_charge_rate')

bashio::log.info "Battery Test Control - Action: ${ACTION}"

# Export config as environment variables for the test script
export FRONIUS_HOST
export MQTT_BROKER
export MQTT_BROKER_PORT
export MQTT_TOPIC_PREFIX
export MQTT_USERNAME
export MQTT_PASSWORD
export MAX_BATTERY_CHARGE_RATE

case "$ACTION" in
    "start")
        TEST_CHARGE_RATE=$((MAX_BATTERY_CHARGE_RATE / 2))
        bashio::log.info "🔋 Starting battery test charge (${TEST_CHARGE_RATE}W - 50% of max ${MAX_BATTERY_CHARGE_RATE}W)"
        python3 /app/simple_battery_test.py "$ACTION"
        ;;
    "stop")
        bashio::log.info "🛑 Stopping battery test charge"
        python3 /app/simple_battery_test.py "$ACTION"
        ;;
    "status")
        bashio::log.info "📊 Checking battery status"
        python3 /app/simple_battery_test.py "$ACTION"
        ;;
    *)
        bashio::log.error "Invalid action: ${ACTION}. Use: start, stop, or status"
        exit 1
        ;;
esac

bashio::log.info "Battery test action '${ACTION}' completed"

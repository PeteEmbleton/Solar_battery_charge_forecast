#!/usr/bin/with-contenv bashio

# ==============================================================================
# Solar Forecast Add-on startup script
# Runs MQTT discovery on container start, then starts the main service
# ==============================================================================

set -e

bashio::log.info "Starting Solar Forecast Add-on..."

# Get configuration values
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

# Wait a bit for MQTT broker to be ready
bashio::log.info "Waiting for MQTT broker to be ready..."
sleep 10

# Run MQTT Discovery once on startup
bashio::log.info "Running MQTT Discovery for sensor creation..."
python3 /app/mqtt_discovery.py \
    --mqtt_broker "${MQTT_BROKER}" \
    --mqtt_broker_port "${MQTT_BROKER_PORT}" \
    --mqtt_topic_prefix "${MQTT_TOPIC_PREFIX}" \
    --mqtt_username "${MQTT_USERNAME}" \
    --mqtt_password "${MQTT_PASSWORD}" \
    --retry_attempts 5 \
    --retry_delay 10

if [ $? -eq 0 ]; then
    bashio::log.info "MQTT Discovery completed successfully"
else
    bashio::log.warning "MQTT Discovery failed, but continuing with main service"
fi

# Get cron schedule from config
CRON_SCHEDULE=$(bashio::config 'cron_schedule')

# Create the cron command
CRON_CMD="python3 /app/full_forecast_and_reccomendation.py \
    --ha_url=\"${HA_URL}\" \
    --ha_token=\"${HA_TOKEN}\" \
    --system_size_kw=\"${SYSTEM_SIZE_KW}\" \
    --battery_size_kwh=\"${BATTERY_SIZE_KWH}\" \
    --minimum_soc_percent=\"${MINIMUM_SOC_PERCENT}\" \
    --minimum_soc_by_sunset=\"${MINIMUM_SOC_BY_SUNSET}\" \
    --cheap_power_window_start=\"${CHEAP_POWER_WINDOW_START}\" \
    --cheap_power_window_end=\"${CHEAP_POWER_WINDOW_END}\" \
    --fronius_host=\"${FRONIUS_HOST}\" \
    --cache_forecast=\"${CACHE_FORECAST}\" \
    --cache_duration=\"${CACHE_DURATION}\" \
    --battery_charge_efficiency=\"${BATTERY_CHARGE_EFFICIENCY}\" \
    --ha_days_to_retrieve=\"${HA_DAYS_TO_RETRIEVE}\" \
    --HA_battery_charge_rate_sensor=\"${HA_BATTERY_CHARGE_RATE_SENSOR}\" \
    --HA_battery_SOC_sensor=\"${HA_BATTERY_SOC_SENSOR}\" \
    --HA_power_usage_sensor=\"${HA_POWER_USAGE_SENSOR}\" \
    --mqtt_broker=\"${MQTT_BROKER}\" \
    --mqtt_broker_port=\"${MQTT_BROKER_PORT}\" \
    --mqtt_topic_prefix=\"${MQTT_TOPIC_PREFIX}\" \
    --mqtt_username=\"${MQTT_USERNAME}\" \
    --mqtt_password=\"${MQTT_PASSWORD}\" \
    --max_battery_charge_rate=\"${MAX_BATTERY_CHARGE_RATE}\""

# Set up cron job
bashio::log.info "Setting up cron job with schedule: ${CRON_SCHEDULE}"
echo "${CRON_SCHEDULE} ${CRON_CMD}" > /etc/crontabs/root

# Make sure crontab file has correct permissions
chmod 0600 /etc/crontabs/root

# Make scripts executable
chmod +x /app/full_forecast_and_reccomendation.py
chmod +x /app/mqtt_discovery.py
chmod +x /app/simple_battery_test.py

# Start cron daemon and keep container running
bashio::log.info "Starting cron daemon..."
exec crond -f -l 8

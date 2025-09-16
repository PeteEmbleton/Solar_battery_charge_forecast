#!/usr/bin/with-contenv bashio

# Get config values
CONFIG_PATH=/data/options.json

# get cron schedule
CRON_SCHEDULE=$(bashio::config "cron_schedule")

# Create the cron command
CRON_CMD="python3 /app/full_forecast_and_reccomendation.py \
    --system_size_kw=\"$(bashio::config 'system_size_kw')\" \
    --battery_size_kwh=\"$(bashio::config 'battery_size_kwh')\" \
    --minimum_soc_percent=\"$(bashio::config 'minimum_soc_percent')\" \
    --minimum_soc_by_sunset=\"$(bashio::config 'minimum_soc_by_sunset')\" \
    --cheap_power_window_start=\"$(bashio::config 'cheap_power_window_start')\" \
    --cheap_power_window_end=\"$(bashio::config 'cheap_power_window_end')\" \
    --fronius_host=\"$(bashio::config 'fronius_host')\" \
    --cache_forecast=\"$(bashio::config 'cache_forecast')\" \
    --cache_duration=\"$(bashio::config 'cache_duration')\" \
    --battery_charge_efficiency=\"$(bashio::config 'battery_charge_efficiency')\" \
    --ha_days_to_retrieve=\"$(bashio::config 'ha_days_to_retrieve')\"\
    --ha_url=\"$(bashio::config 'ha_url')\" \
    --ha_token=\"$(bashio::config 'ha_token')\" \
    --HA_battery_charge_rate_sensor=\"$(bashio::config 'HA_battery_charge_rate_sensor')\" \
    --HA_battery_SOC_sensor=\"$(bashio::config 'HA_battery_SOC_sensor')\" \
    --HA_power_usage_sensor=\"$(bashio::config 'HA_power_usage_sensor')\" \
    --mqtt_broker=\"$(bashio::config 'mqtt_broker')\" \
    --mqtt_broker_port=\"$(bashio::config 'mqtt_broker_port')\" \
    --mqtt_username=\"$(bashio::config 'mqtt_username')\" \
    --mqtt_password=\"$(bashio::config 'mqtt_password')\" \
    --mqtt_topic_prefix=\"$(bashio::config 'mqtt_topic_prefix')\""

# Write to crontab with proper format
echo "${CRON_SCHEDULE} ${CRON_CMD}" > /etc/crontabs/root

# Make sure crontab file has correct permissions
chmod 0600 /etc/crontabs/root
chmod +x /app/full_forecast_and_reccomendation.py

# Start cron daemon
crond -f -l 8
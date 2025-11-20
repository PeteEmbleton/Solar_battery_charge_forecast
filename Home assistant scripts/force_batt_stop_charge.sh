#!/bin/sh

# Set your add-on slug
ADDON_SLUG="local_solar_forecast_battery"

# Set your desired manual_action (start, stop, status, etc.)
NEW_ACTION="stop"

# Get current options from Supervisor API
CURRENT_OPTIONS=$(curl -s -X GET \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  http://supervisor/addons/$ADDON_SLUG/info | jq '.data.options')

# Update manual_action in the options JSON
UPDATED_OPTIONS=$(echo "$CURRENT_OPTIONS" | jq --arg action "$NEW_ACTION" '.manual_action = $action')

# Send updated options back to Supervisor
curl -X POST \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"options\": $UPDATED_OPTIONS}" \
  http://supervisor/addons/$ADDON_SLUG/options

# Restart the add-on to trigger the action
curl -X POST \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/addons/$ADDON_SLUG/restart
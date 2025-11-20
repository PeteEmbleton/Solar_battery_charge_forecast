# Home Assistant Script for Battery Charging Management

This guide outlines how to set up and use a script in Home Assistant that stops forced battery charging if mains power is lost.

## Setup Instructions

### Step 1: Prepare the Environment

1. **Create a Scripts Folder**  
   Create a directory named `scripts` within your configuration folder where you store your scripts.

2. **Copy the Script**  
   Place the script file `force_batt_stop_charge.sh` into this newly created `scripts` folder.

3. **Make the Script Executable**  
   Run the following command to make the script executable:
   ```bash
   chmod +x force_batt_stop_charge.sh
   ```

### Step 2: Update Home Assistant Configuration

Add a shell command to your `configuration.yaml` file:

```yaml
shell_command:
  force_batt_stop_charging_script: "/bin/bash scripts/force_batt_stop_charge.sh"
```

### Step 3: Create an Automation

Below is an example automation that triggers the script when mains power is lost.

```yaml
alias: Stop Charging if Power is Lost
description: "Automatically stops battery charging upon loss of mains power."
trigger:
  - platform: state
    entity_id: sensor.smart_meter_63a_1_meter_location
    from: null
    to: unknown
conditions: []
actions:
  - service: shell_command.force_batt_stop_charging_script
    response_variable: script_result
  - service: persistent_notification.create
    data:
      title: "Script Execution Result"
      message: |
        Reset Battery Charging Script Called. Response: {{ script_result }}
    enabled: false
mode: single
```

## Summary

- **Objective**: This setup ensures that battery charging is halted when mains power becomes unavailable, preventing potential damage or inefficiency.
  
- **Automation Triggers**: The automation monitors a specific sensor for changes indicating loss of power (`sensor.smart_meter_63a_1_meter_location`).

By following these steps, you can effectively manage your system's response to power disruptions using Home Assistant.
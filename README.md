# Solar Forecast and Battery Control for Fronius Inverters

**Home Assistant add-on for intelligent solar forecasting and automated battery charging control.**

Specifically designed for **Fronius inverters** with Modbus TCP control. Tested with BYD batteries but should work with any Fronius-compatible battery system.

## ✨ Key Features

- **🌞 Solar Production Forecasting** - Uses Open-Meteo weather data to predict tomorrow's solar generation
- **🔋 Smart Battery Management** - Automatically charges from grid during cheap power windows when needed
- **⚡ Fronius Inverter Control** - Direct Modbus TCP integration for seamless battery charging control
- **📊 MQTT Discovery** - Auto-creates sensors in Home Assistant for monitoring and automation
- **🏠 Power Usage Prediction** - Learns from your historical consumption patterns
- **🌅 Sun Integration** - Uses Home Assistant's sunrise/sunset data for optimal timing
- **📈 Real-time Monitoring** - Comprehensive status updates via MQTT

## 🎯 How It Works

1. **Analyzes** your historical power usage patterns
2. **Forecasts** tomorrow's solar production using weather data
3. **Calculates** if you need to charge the battery overnight
4. **Automatically controls** your Fronius inverter during cheap power windows
5. **Publishes** all data to Home Assistant via MQTT for monitoring and automation

## 🔧 Compatible Hardware

- **Fronius inverters** with Modbus TCP enabled
- **BYD batteries** (tested)
- Any battery system compatible with Fronius inverters
- Home Assistant with MQTT integration.

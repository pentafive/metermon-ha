# metermon-ha

`metermon-ha` is a Dockerized wrapper around [rtlamr](https://github.com/bemasher/rtlamr) that automatically integrates with Home Assistant using MQTT Discovery. It connects to an existing `rtl_tcp` instance, receives meter readings, and publishes them to MQTT topics in a format that Home Assistant understands, creating sensors dynamically without any manual configuration in Home Assistant.

**This project is a fork of [seanauff/metermon](https://github.com/seanauff/metermon), modified for direct Home Assistant integration via MQTT Discovery.  All credit for the original `metermon` and the underlying `rtlamr` goes to their respective authors.  This fork builds upon their excellent work.**

**Original rtlamr project by bemasher: [https://github.com/bemasher/rtlamr](https://github.com/bemasher/rtlamr)**

**Original metermon project by seanauff: [https://github.com/seanauff/metermon](https://github.com/seanauff/metermon)**


## Advantages over the Original `metermon`

*   **Automatic Sensor Creation:** No need to manually define sensors in Home Assistant's `configuration.yaml`.  Sensors are created automatically via MQTT Discovery.
*   **Simplified Setup:**  No complex Home Assistant automations are required.
*   **Robustness:**  Handles reconnects and restarts gracefully.
*   **Efficiency:**  Minimizes MQTT message overhead.

## Prerequisites

1.  **MQTT Broker:** You need a running MQTT broker (e.g., Mosquitto).  Home Assistant's built-in broker works fine.
2.  **`rtl_tcp` Instance:** You need a running `rtl_tcp` instance, accessible from the `metermon-ha` container. This typically involves an RTL-SDR USB dongle.  See the original `metermon` README or the `rtlamr` documentation for details on setting up `rtl_tcp`.
3.  **Docker and Docker Compose (Recommended):** While you can run the container directly with `docker run`, using Docker Compose is highly recommended for easier management.
4. **Home Assistant:** with the MQTT integration set.

## Installation and Configuration

### 1. Docker Compose (Recommended)

Create a `docker-compose.yml` file (or add to an existing one) with the following content, adjusting the values as needed for your environment:

```yaml
version: '3.7'
services:
  metermon-ha:  # Changed container and service name
    image: pentafive/metermon-ha:latest  #  <-- USE YOUR IMAGE HERE
    container_name: metermon-ha  # Changed container name
    environment:
      - MQTT_BROKER_HOST=your_mqtt_broker_ip #  <-- CHANGE THIS
      - MQTT_BROKER_PORT=1883                #  <-- Change if necessary
      - MQTT_CLIENT_ID=metermon-ha          #  Change if you have conflicts
      - MQTT_USERNAME=your_mqtt_username    #  <-- CHANGE THIS (if needed)
      - MQTT_PASSWORD=your_mqtt_password    #  <-- CHANGE THIS (if needed, and use secrets!)
      - MQTT_TOPIC_PREFIX=metermon          #  You can change this if you want
      - RTL_TCP_SERVER=your_rtl_tcp_ip:1234 #  <-- CHANGE THIS
      - RTLAMR_MSGTYPE=all                #  Customize as needed
      #- RTLAMR_FILTERID=                   # Optional: Filter by meter ID
      #- RTLAMR_SYMBOLLENGTH=72    # Optional: for performance tuning
      - RTLAMR_UNIQUE=true          #  Recommended
      #- METERMON_ELECTRIC_DIVISOR=100.0   # Keep if you need it.
      - METERMON_WATER_DIVISOR=10.0        # Keep if you need it.
    restart: unless-stopped
    # Remove depends_on and devices as they are not needed in your setup
    # depends_on:
    #  - rtl_tcp  <- Removed.
    # devices:
    # - /dev/bus/usb:/dev/bus/usb <- Removed

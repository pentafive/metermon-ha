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

#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import time
import select  # Import the select module
import paho.mqtt.client as mqtt

# --- Constants ---
UNIT_KWH = "kWh"
UNIT_GALLONS = "gal"
UNIT_CUBIC_FEET = "ft^3"
METER_TYPE_ELECTRIC = "Electric"
METER_TYPE_WATER = "Water"
METER_TYPE_GAS = "Gas"
PROTOCOL_SCM = "SCM"
PROTOCOL_SCM_PLUS = "SCM+"
PROTOCOL_IDM = "IDM"
PROTOCOL_NETIDM = "NetIDM"
PROTOCOL_R900 = "R900"
PROTOCOL_R900BCD = "R900BCD"
RTLAMR_RESTART_DELAY = 10 #seconds to wait before restarting rtlamr

# --- Environment Variable Configuration ---
MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', "127.0.0.1")
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))
MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', "metermon-ha")
MQTT_USERNAME = os.getenv('MQTT_USERNAME')  # Optional, defaults to None
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')  # Optional, defaults to None
MQTT_TOPIC_PREFIX = os.getenv('MQTT_TOPIC_PREFIX', "metermon-ha")
RTL_TCP_SERVER = os.getenv('RTL_TCP_SERVER', "127.0.0.1:1234")
RTLAMR_MSGTYPE = os.getenv('RTLAMR_MSGTYPE', "all")
RTLAMR_FILTERID = os.getenv('RTLAMR_FILTERID')  # Optional, defaults to None
RTLAMR_UNIQUE = os.getenv('RTLAMR_UNIQUE', "true")
METERMON_ELECTRIC_DIVISOR = float(os.getenv('METERMON_ELECTRIC_DIVISOR', 100.0))
METERMON_WATER_DIVISOR = float(os.getenv('METERMON_WATER_DIVISOR', 10.0))
RTLSDR_READ_TIMEOUT = float(os.getenv('RTLSDR_READ_TIMEOUT', 5.0))  # Timeout in seconds, default 5.

# --- Validation ---
if not MQTT_BROKER_HOST:
    print("Error: MQTT_BROKER_HOST environment variable not set.")
    sys.exit(1)
# You might want similar checks for other *critical* variables.

# --- R900 Lookup Tables and Attributes ---
R900_LOOKUP = {
    "HISTORY": {
        0: "0",
        1: "1-2",
        2: "3-7",
        3: "8-14",
        4: "15-21",
        5: "22-34",
        6: "35+",
    },
    "INTENSITY": {
        0: "None",
        1: "Low",
        2: "High",
    }
}
R900_ATTRIBS = {
    "Leak": "HISTORY",
    "NoUse": "HISTORY",
    "BackFlow": "INTENSITY",
    "LeakNow": "INTENSITY",
}



class Meter:
    """Represents a utility meter."""

    def __init__(self, meter_id, meter_type, protocol, client, mqtt_topic_prefix):
        """Initializes a Meter object.

        Args:
            meter_id: The meter's ID.
            meter_type: The type of meter (Electric, Water, Gas).
            protocol: The communication protocol used by the meter.
            client: The MQTT client object.
            mqtt_topic_prefix:  The base MQTT topic prefix.
        """
        self.meter_id = meter_id
        self.meter_type = meter_type
        self.protocol = protocol
        self.client = client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.configured = False
        # Pre-calculate base device config (shared between sensors)
        self._base_device_config = {
            "identifiers": [f"metermon-ha_{self.meter_id}"],
            "name": f"Metermon-HA {self.meter_id}",
            "model": f"{self.meter_type.capitalize()} Meter",
            "manufacturer": "Metermon"
        }

    def _publish_config(self, entity_type, entity_id, config_payload):
        """Publishes a Home Assistant MQTT discovery configuration message.

        Args:
            entity_type:  "sensor" or "binary_sensor".
            entity_id: The unique ID of the entity within its type (e.g., "consumption").
            config_payload:  The JSON payload for the configuration.
        """
        config_topic = f"homeassistant/{entity_type}/{self.meter_id}/{entity_id}/config"
        self.client.publish(config_topic, json.dumps(config_payload), qos=1, retain=True)

    def configure_sensors(self, unit):
        """Configures Home Assistant sensors for the meter (if not already configured)."""
        if self.configured:
            return

        # --- Consumption Sensor ---
        consumption_config = {
            "name": f"{self.meter_type.capitalize()} Consumption",
            "state_topic": f"homeassistant/sensor/{self.meter_id}/{self.meter_type}_consumption/state",
            "unit_of_measurement": unit,
            "unique_id": f"metermon-ha_{self.meter_id}_{self.meter_type}_consumption",
            "device": self._base_device_config,
            "state_class": "total_increasing",
            "device_class": self.meter_type.lower() if self.meter_type.lower() in ['water', 'gas', 'electric'] else None,
            "availability_topic": f"{self.mqtt_topic_prefix}/status",
            "payload_available": "Online",
            "payload_not_available": "Offline"
        }
        self._publish_config("sensor", f"{self.meter_type}_consumption", consumption_config)

        # --- Leak Binary Sensor ---
        leak_config = {
            "name": "Leak",
            "state_topic": f"homeassistant/binary_sensor/{self.meter_id}/leak/state",
            "value_template": "{{ 'ON' if value_json.leak_now != 'None' else 'OFF' }}",
            "unique_id": f"metermon-ha_{self.meter_id}_leak",
            "device": self._base_device_config,
            "device_class": "problem",
            "availability_topic": f"{self.mqtt_topic_prefix}/status",
            "payload_available": "Online",
            "payload_not_available": "Offline"
        }
        self._publish_config("binary_sensor", "leak", leak_config)


        # --- Config Check Binary Sensor ---
        config_check_config = {
            "name": f"Metermon-HA {self.meter_id} {self.meter_type.capitalize()} Config",
            "state_topic": f"homeassistant/binary_sensor/{self.meter_id}/{self.meter_type}_consumption_config/state",
            "value_template": "{{ 'ON' }}",
            "unique_id": f"metermon-ha_{self.meter_id}_{self.meter_type}_consumption_config",
            "availability_topic": f"{self.mqtt_topic_prefix}/status",
            "payload_available": "Online",
            "payload_not_available": "Offline",
            "device_class": "connectivity"
        }
        self._publish_config("binary_sensor", f"{self.meter_type}_consumption_config", config_check_config)
        config_state_topic = f"homeassistant/binary_sensor/{self.meter_id}/{self.meter_type}_consumption_config/state"
        self.client.publish(config_state_topic, payload="ON", qos=1, retain=False)  # Use qos=1 for config

        self.configured = True
        print(f"Configured sensors for meter: {self.meter_id}_{self.meter_type}")

    def publish_state(self, consumption, leak_now="None"):
        """Publishes the current state of the meter to MQTT."""
        consumption_state_topic = f"homeassistant/sensor/{self.meter_id}/{self.meter_type}_consumption/state"
        self.client.publish(consumption_state_topic, payload=str(consumption), qos=0, retain=False)  # qos=0 for state updates

        leak_state_topic = f"homeassistant/binary_sensor/{self.meter_id}/leak/state"
        leak_state_payload = json.dumps({
            "consumption": consumption,
            "leak_now": leak_now
        })
        self.client.publish(leak_state_topic, leak_state_payload, qos=0, retain=False) # qos=0 for state updates
        print(f"Published state update for meter: {self.meter_id}_{self.meter_type}")


def on_connect(client, userdata, flags, reason_code, properties):
    """MQTT connection callback."""
    print(f"Connected to broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} with reason code {reason_code}: {mqtt.connack_string(reason_code)}")
    client.publish(MQTT_TOPIC_PREFIX + "/status", payload="Online", qos=1, retain=True)  # Use qos=1 for status

def on_disconnect(client, userdata, flags, reason_code, properties):
    """MQTT disconnection callback."""
    if reason_code != 0:
        print(f"Unexpected disconnection from broker (RC={reason_code}). Attempting to reconnect...")

# --- MQTT Client Setup ---
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
if MQTT_USERNAME and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    print("Username and password set.")
client.will_set(MQTT_TOPIC_PREFIX + "/status", payload="Offline", qos=1, retain=True)  # Use qos=1 for LWT
client.on_connect = on_connect
client.on_disconnect = on_disconnect

# --- Connect to Broker ---
client.connect(MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
client.loop_start()

# --- Start RTLAMR ---
#moved into function

# --- Main Loop ---
meters = {}  # Dictionary to store Meter objects
last_rtl_restart = 0 #track the time of the last rtlamr restart

def start_rtlamr():
    """Starts the rtlamr subprocess."""
    cmdargs = [
        'rtlamr',
        '-format=json',
        f'-server={RTL_TCP_SERVER}',
        f'-msgtype={RTLAMR_MSGTYPE}',
        f'-unique={RTLAMR_UNIQUE}',
    ]
    if RTLAMR_FILTERID:
        cmdargs.append(f'-filterid={RTLAMR_FILTERID}')

    print(f"Starting rtlamr with command: {' '.join(cmdargs)}")
    return subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # Capture stderr too

def process_line(line):
    """Processes a single line of output from rtlamr."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        print(f"Error decoding JSON: {line.decode()}") # .decode() for printing
        return

    msg = {
        "Protocol": "Unknown",
        "Time": "Unknown",
        "Type": "Unknown",
        "ID": "Unknown",
        "Consumption": 0,
        "Unit": "Unknown",
        "LeakNow": "None"
    }

    msg['Protocol'] = data['Type']
    msg['Time'] = data['Time']

    if msg['Protocol'] == PROTOCOL_SCM:
        msg['ID'] = str(data['Message']['ID'])
        if data['Message']['Type'] in (4, 5, 7, 8):
            msg['Type'] = METER_TYPE_ELECTRIC
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_ELECTRIC_DIVISOR
            msg['Unit'] = UNIT_KWH
        elif data['Message']['Type'] in (2, 9, 12):
            msg['Type'] = METER_TYPE_GAS
            msg['Consumption'] = data['Message']['Consumption']
            msg['Unit'] = UNIT_CUBIC_FEET
        elif data['Message']['Type'] in (3, 11, 13):
            msg['Type'] = METER_TYPE_WATER
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
            msg['Unit'] = UNIT_GALLONS

    elif msg['Protocol'] == PROTOCOL_SCM_PLUS:
        msg['ID'] = str(data['Message']['EndpointID'])
        if data['Message']['EndpointType'] in (4, 5, 7, 8, 110):
            msg['Type'] = METER_TYPE_ELECTRIC
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_ELECTRIC_DIVISOR
            msg['Unit'] = UNIT_KWH
        elif data['Message']['EndpointType'] in (2, 9, 12, 156, 188, 220):
            msg['Type'] = METER_TYPE_GAS
            msg['Consumption'] = data['Message']['Consumption']
            msg['Unit'] = UNIT_CUBIC_FEET
        elif data['Message']['EndpointType'] in (3, 11, 13, 27, 171):
            msg['Type'] = METER_TYPE_WATER
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
            msg['Unit'] = UNIT_GALLONS
        msg['LeakNow'] = "None" if data['Message'].get('Leak') is None else "Leak"

    elif msg['Protocol'] == PROTOCOL_IDM:
        msg['Type'] = METER_TYPE_ELECTRIC
        msg['ID'] = str(data['Message']['ERTSerialNumber'])
        msg['Consumption'] = data['Message']['LastConsumptionCount'] / METERMON_ELECTRIC_DIVISOR
        msg['Unit'] = UNIT_KWH

    elif msg['Protocol'] == PROTOCOL_NETIDM:
        msg['Type'] = METER_TYPE_ELECTRIC
        msg['ID'] = str(data['Message']['ERTSerialNumber'])
        msg['Consumption'] = data['Message']['LastConsumptionNet'] / METERMON_ELECTRIC_DIVISOR
        msg['Unit'] = UNIT_KWH

    elif msg['Protocol'] == PROTOCOL_R900:
        msg['Type'] = METER_TYPE_WATER
        msg['ID'] = str(data['Message']['ID'])
        msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
        msg['Unit'] = UNIT_GALLONS
        for attr, kind in R900_ATTRIBS.items():
            value = data['Message'].get(attr)
            if value is not None:
                try:
                    msg[attr] = R900_LOOKUP[kind][value]
                except KeyError:
                    print(f"Could not process R900 value ({attr}: {value})")

    elif msg['Protocol'] == PROTOCOL_R900BCD:
        msg['Type'] = METER_TYPE_WATER
        msg['ID'] = str(data['Message']['ID'])
        msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
        msg['Unit'] = UNIT_GALLONS

    if msg['Consumption'] >= 0:
        meter_id = msg['ID']
        meter_type = msg['Type'].lower()
        meter_key = f"{meter_id}_{meter_type}"

        if meter_key not in meters:
            meter = Meter(meter_id, meter_type, msg['Protocol'], client, MQTT_TOPIC_PREFIX)
            meters[meter_key] = meter
            meter.configure_sensors(msg['Unit'])

        meters[meter_key].publish_state(msg['Consumption'], msg.get("LeakNow", "None"))

proc = start_rtlamr() #start rtlamr

while True:
    ready, _, _ = select.select([proc.stdout, proc.stderr], [], [], RTLSDR_READ_TIMEOUT)  # Watch stdout and stderr
    if ready:
        for source in ready:

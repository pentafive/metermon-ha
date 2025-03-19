#!/usr/bin/python
import os
import sys
import json
import subprocess
import time
import paho.mqtt.client as mqtt

# read in needed env variables
MQTT_BROKER_HOST  = os.getenv('MQTT_BROKER_HOST',"127.0.0.1")
MQTT_BROKER_PORT  = int(os.getenv('MQTT_BROKER_PORT',1883))
MQTT_CLIENT_ID    = os.getenv('MQTT_CLIENT_ID',"metermon-ha")
MQTT_USERNAME      = os.getenv('MQTT_USERNAME',"")
MQTT_PASSWORD      = os.getenv('MQTT_PASSWORD',"")
MQTT_TOPIC_PREFIX = os.getenv('MQTT_TOPIC_PREFIX',"metermon-ha")  # Keep this for availability
RTL_TCP_SERVER    = os.getenv('RTL_TCP_SERVER',"127.0.0.1:1234")
RTLAMR_MSGTYPE    = os.getenv('RTLAMR_MSGTYPE',"all")
RTLAMR_FILTERID   = os.getenv('RTLAMR_FILTERID',"") # Optional filter ID
RTLAMR_UNIQUE     = os.getenv('RTLAMR_UNIQUE',"true")
METERMON_ELECTRIC_DIVISOR = float(os.getenv('METERMON_ELECTRIC_DIVISOR',100.0))
METERMON_WATER_DIVISOR = float(os.getenv('METERMON_WATER_DIVISOR', 10.0))

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

# Dictionary to track configured meters (key = meterID_meterType)
configured_meters = {}

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    # print connection statement
    print(f"Connected to broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} with reason code {reason_code}: "+mqtt.connack_string(reason_code))

    # set mqtt status message
    client.publish(MQTT_TOPIC_PREFIX+"/status",payload="Online",qos=1,retain=True)

def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(f"Unexpected disconnection from broker (RC={reason_code}). Attempting to reconnect...")

# set up mqtt client
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,client_id=MQTT_CLIENT_ID)
if MQTT_USERNAME and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USERNAME,MQTT_PASSWORD)
    print("Username and password set.")
client.will_set(MQTT_TOPIC_PREFIX+"/status", payload="Offline", qos=1, retain=True) # set LWT
client.on_connect = on_connect # on connect callback
client.on_disconnect = on_disconnect # on disconnect callback

# connect to broker
client.connect(MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
client.loop_start()

# start RTLAMR
cmdargs = [
    'rtlamr',
    '-format=json',
    f'-server={RTL_TCP_SERVER}',
    f'-msgtype={RTLAMR_MSGTYPE}',
    f'-unique={RTLAMR_UNIQUE}',
]
if RTLAMR_FILTERID:
   cmdargs.append(f'-filterid={RTLAMR_FILTERID}')

proc = subprocess.Popen(cmdargs, stdout=subprocess.PIPE)

# read output of RTLAMR
while True:
    line = proc.stdout.readline()
    if not line:
        break
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        print(f"Error decoding JSON: {line}")
        continue

    msg = {
        "Protocol": "Unknown",
        "Time": "Unknown",
        "Type": "Unknown",
        "ID": "Unknown",
        "Consumption": 0,
        "Unit": "Unknown",
        "LeakNow": "None"
    }

    # set Protocol
    msg['Protocol'] = data['Type']
    msg['Time'] = data['Time']

    # SCM messages
    if msg['Protocol'] == "SCM":
        msg['ID'] = str(data['Message']['ID'])
        if data['Message']['Type'] in (4, 5, 7, 8):  # electric meter
            msg['Type'] = "Electric"
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_ELECTRIC_DIVISOR
            msg['Unit'] = "kWh"
        elif data['Message']['Type'] in (2, 9, 12):  # gas meter
            msg['Type'] = "Gas"
            msg['Consumption'] = data['Message']['Consumption']
            msg['Unit'] = "ft^3"
        elif data['Message']['Type'] in (3, 11, 13):  # water meter
            msg['Type'] = "Water"
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
            msg['Unit'] = "gal"
    # SCM+ messages
    elif msg['Protocol'] == "SCM+":
        msg['ID'] = str(data['Message']['EndpointID'])
        if data['Message']['EndpointType'] in (4, 5, 7, 8, 110):  # electric meter
            msg['Type'] = "Electric"
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_ELECTRIC_DIVISOR
            msg['Unit'] = "kWh"
        elif data['Message']['EndpointType'] in (2, 9, 12, 156, 188, 220):  # gas meter
            msg['Type'] = "Gas"
            msg['Consumption'] = data['Message']['Consumption']
            msg['Unit'] = "ft^3"
        elif data['Message']['EndpointType'] in (3, 11, 13, 27, 171):  # water meter
            msg['Type'] = "Water"
            msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
            msg['Unit'] = "gal"
            msg['LeakNow'] = "None" if data['Message'].get('Leak') is None else "Leak"

    # IDM messages
    elif msg['Protocol'] == "IDM":
        msg['Type'] = "Electric"
        msg['ID'] = str(data['Message']['ERTSerialNumber'])
        msg['Consumption'] = data['Message']['LastConsumptionCount'] / METERMON_ELECTRIC_DIVISOR
        msg['Unit'] = "kWh"
    # NetIDM messages
    elif msg['Protocol'] == "NetIDM":
        msg['Type'] = "Electric"
        msg['ID'] = str(data['Message']['ERTSerialNumber'])
        msg['Consumption'] = data['Message']['LastConsumptionNet'] / METERMON_ELECTRIC_DIVISOR
        msg['Unit'] = "kWh"
    # R900 messages
    elif msg['Protocol'] == "R900":
        msg['Type'] = "Water"
        msg['ID'] = str(data['Message']['ID'])
        msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
        msg['Unit'] = "gal"
        for attr, kind in R900_ATTRIBS.items():
            value = data['Message'].get(attr)
            if value is not None:
                try:
                    msg[attr] = R900_LOOKUP[kind][value]
                except KeyError:
                    print(f"Could not process R900 value ({attr}: {value})")

    # R900bcd messages
    elif msg['Protocol'] == "R900BCD":
        msg['Type'] = "Water"
        msg['ID'] = str(data['Message']['ID'])
        msg['Consumption'] = data['Message']['Consumption'] / METERMON_WATER_DIVISOR
        msg['Unit'] = "gal"

    # filter out cases where consumption value is negative
    if msg['Consumption'] >= 0:
        meter_id = msg['ID']
        meter_type = msg['Type'].lower()
        meter_key = f"{meter_id}_{meter_type}"

        if meter_key not in configured_meters:
            # --- Create Consumption Sensor (Configuration Message) ---
            consumption_config_topic = f"homeassistant/sensor/{meter_id}/{meter_type}_consumption/config"  # CORRECTED
            consumption_config_payload = json.dumps({
                "name": f"{meter_id} {meter_type.capitalize()} Consumption",
                "state_topic": f"homeassistant/sensor/{meter_id}/{meter_type}_consumption/state",  # CORRECTED
                "unit_of_measurement": msg['Unit'],
                "unique_id": f"metermon-ha_{meter_id}_{meter_type}_consumption",
                "device": {
                    "identifiers": [f"metermon-ha_{meter_id}"],
                    "name": f"Metermon-HA {meter_id}",
                    "model": f"{meter_type.capitalize()} Meter",
                    "manufacturer": "Metermon"
                },
                "state_class": "total_increasing",
                "device_class": msg['Type'].lower() if msg['Type'].lower() in ['water', 'gas', 'electric'] else None,
                "availability_topic": f"{MQTT_TOPIC_PREFIX}/status",  # Use the prefix
                "payload_available": "Online",
                "payload_not_available": "Offline"
            })
            client.publish(consumption_config_topic, consumption_config_payload, retain=True)

            # --- Create Leak Binary Sensor (Configuration Message) ---
            leak_config_topic = f"homeassistant/binary_sensor/{meter_id}/leak/config"  # CORRECTED
            leak_config_payload = json.dumps({
                "name": f"{meter_id} Leak",
                "state_topic": f"homeassistant/binary_sensor/{meter_id}/leak/state",  # CORRECTED
                "value_template": "{{ 'ON' if value_json.leak_now != 'None' else 'OFF' }}",
                "unique_id": f"metermon-ha_{meter_id}_leak",
                "device": {
                    "identifiers": [f"metermon-ha_{meter_id}"],
                    "name": f"Metermon-HA {meter_id}",
                    "model": f"{meter_type.capitalize()} Meter",
                    "manufacturer": "Metermon"
                },
                "device_class": "problem",
                "availability_topic": f"{MQTT_TOPIC_PREFIX}/status",  # Use the prefix
                "payload_available": "Online",
                "payload_not_available": "Offline"
            })
            client.publish(leak_config_topic, leak_config_payload, retain=True)
          # --- Create Config Check Binary Sensor (Configuration Message) --- #
            config_config_topic = f"homeassistant/binary_sensor/{meter_id}/{meter_type}_consumption_config/config" # CORRECTED
            config_config_payload = json.dumps({
                "name": f"Metermon-HA {meter_id} {meter_type.capitalize()} Config",
                "state_topic": f"homeassistant/binary_sensor/{meter_id}/{meter_type}_consumption_config/state", # CORRECTED
                "value_template": "{{ 'ON' }}",
                "unique_id": f"metermon-ha_{meter_id}_{meter_type}_consumption_config",
                "availability_topic": f"{MQTT_TOPIC_PREFIX}/status",
                "payload_available": "Online",
                "payload_not_available": "Offline",
                "device_class": "connectivity"
            })
            client.publish(config_config_topic, config_config_payload, retain=True)
            #Publish state to config
            config_state_topic = f"homeassistant/binary_sensor/{meter_id}/{meter_type}_consumption_config/state"  # CORRECTED
            client.publish(config_state_topic, payload="ON", retain=False)
            configured_meters[meter_key] = True
            print(f"Configured sensors for meter: {meter_key}")

        # --- Publish State Message for Consumption Sensor ---
        consumption_state_topic = f"homeassistant/sensor/{meter_id}/{meter_type}_consumption/state"  # CORRECTED
        client.publish(consumption_state_topic, payload=str(msg['Consumption']), retain=False)

        # --- Publish State Message for Leak Sensor ---
        leak_state_topic = f"homeassistant/binary_sensor/{meter_id}/leak/state"  # CORRECTED
        leak_state_payload = json.dumps({
            "consumption": msg['Consumption'],
            "leak_now": msg.get("LeakNow", "None")
        })
        client.publish(leak_state_topic, leak_state_payload, retain=False)

        print(f"Published state update for meter: {meter_key}")

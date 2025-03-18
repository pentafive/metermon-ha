# --- Publish State Message for Consumption Sensor ---
        consumption_state_topic = f"homeassistant/sensor/metermon-ha_{meter_id}/{meter_type}_consumption/state" # Added -ha
        client.publish(consumption_state_topic, payload=str(msg['Consumption']), retain=False) # Just the value!

        # --- Publish State Message for Leak Sensor ---
        leak_state_topic = f"homeassistant/sensor/metermon-ha_{meter_id}/{meter_type}_consumption/state"  #  <-- CORRECTED!
        leak_state_payload = json.dumps({
            "consumption": msg['Consumption'],
            "leak_now": msg.get("LeakNow", "None")  # Use .get() for safety
        })
        client.publish(leak_state_topic, leak_state_payload, retain=False)

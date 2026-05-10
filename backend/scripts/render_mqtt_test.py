"""
One-off MQTT connectivity test for Render (or local) using env vars.
Usage (Render one-off job):
  python backend/scripts/render_mqtt_test.py

Locally (PowerShell):
  $env:HOME_MQTT_HOST='...'; $env:HOME_MQTT_PORT='8883'; $env:HOME_MQTT_USERNAME='user'; $env:HOME_MQTT_PASSWORD='pass'; python backend/scripts/render_mqtt_test.py
"""
import os
import ssl
import time
import sys

try:
    import paho.mqtt.client as mqtt
except Exception as e:
    print('Missing dependency paho-mqtt:', e)
    sys.exit(2)

HOST = os.getenv('HOME_MQTT_HOST')
PORT = int(os.getenv('HOME_MQTT_PORT', '8883'))
USER = os.getenv('HOME_MQTT_USERNAME')
PWD = os.getenv('HOME_MQTT_PASSWORD')
CID = os.getenv('HOME_MQTT_CLIENT_ID', 'zara-backend-test')
TLS_ENABLED = os.getenv('HOME_MQTT_TLS_ENABLED', 'false').lower() in ('1','true','yes')
TLS_INSECURE = os.getenv('HOME_MQTT_TLS_INSECURE', 'false').lower() in ('1','true','yes')

if not HOST:
    print('HOME_MQTT_HOST is not set')
    sys.exit(2)

print('Testing MQTT connectivity to', HOST, 'port', PORT)

def on_connect(client, userdata, flags, rc):
    print('on_connect rc=', rc)

def on_disconnect(client, userdata, rc):
    print('on_disconnect rc=', rc)

client = mqtt.Client(client_id=CID, protocol=mqtt.MQTTv311)
client.on_connect = on_connect
client.on_disconnect = on_disconnect

if USER or PWD:
    client.username_pw_set(USER, PWD)

if TLS_ENABLED:
    try:
        context = ssl.create_default_context()
        if TLS_INSECURE:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        client.tls_set_context(context)
        print('TLS enabled (insecure=%s)' % TLS_INSECURE)
    except Exception as e:
        print('Failed to configure TLS:', e)
        sys.exit(2)

try:
    client.connect(HOST, PORT, 10)
except Exception as e:
    print('Connect exception:', e)
    sys.exit(1)

client.loop_start()
time.sleep(3)
client.loop_stop()
client.disconnect()
print('Done')

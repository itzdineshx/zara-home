import paho.mqtt.client as mqtt
import time
import uuid

HOST = "e5c35c674acb4ec6bdb8514fa465cfa6.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "zaraai"
PASSWORD = "Reddragon123"
TOPIC = "zara/home/control"

connected = False

def on_connect(client, userdata, flags, rc):
    global connected
    print("on_connect rc=", rc)
    connected = (rc == 0)

def on_disconnect(client, userdata, rc):
    print("on_disconnect rc=", rc)

client_id = f"zara-test-{uuid.uuid4().hex[:6]}"
client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
client.username_pw_set(USERNAME, PASSWORD)

# Use default system CA, allow insecure if broker uses self-signed
try:
    client.tls_set()
except Exception as e:
    print("tls_set() warning:", e)

try:
    client.tls_insecure_set(True)
except Exception:
    pass

client.on_connect = on_connect
client.on_disconnect = on_disconnect

print(f"Connecting to {HOST}:{PORT} as {USERNAME}... (client_id={client_id})")
try:
    client.connect(HOST, PORT, keepalive=30)
except Exception as exc:
    print("Connect exception:", exc)
    raise

client.loop_start()

# wait for connect
for i in range(10):
    if connected:
        break
    print("waiting for connect...", i)
    time.sleep(0.5)

if not connected:
    print("Failed to connect to MQTT broker")
else:
    payload = '{"action":"status_check","source":"zara-test"}'
    print("Publishing test payload to", TOPIC)
    result = client.publish(TOPIC, payload, qos=1)
    print("publish rc:", result.rc)
    try:
        result.wait_for_publish(timeout=2.0)
        print("published?", result.is_published())
    except Exception as e:
        print("publish wait exception:", e)

time.sleep(0.5)
client.loop_stop()
client.disconnect()
print("Done")

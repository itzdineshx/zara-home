from __future__ import annotations

import os
import signal
import sys
import threading
import time
import uuid

import paho.mqtt.client as mqtt

HOST = os.getenv("HOME_MQTT_HOST", "e5c35c674acb4ec6bdb8514fa465cfa6.s1.eu.hivemq.cloud")
PORT = int(os.getenv("HOME_MQTT_PORT", "8883"))
USERNAME = os.getenv("HOME_MQTT_USERNAME", "zaraai")
PASSWORD = os.getenv("HOME_MQTT_PASSWORD", "Reddragon123")
TOPIC = os.getenv("HOME_MQTT_CONTROL_TOPIC", "zara/home/control")
TIMEOUT_S = float(os.getenv("MQTT_SUBSCRIBER_TIMEOUT_S", "30"))
MESSAGE_LIMIT = int(os.getenv("MQTT_SUBSCRIBER_MESSAGE_LIMIT", "2"))

stop_event = threading.Event()
received: list[str] = []


def on_connect(client: mqtt.Client, _userdata, _flags, rc):
    print(f"on_connect rc={rc}")
    if rc == 0:
        client.subscribe(TOPIC, qos=1)
        print(f"subscribed {TOPIC}")
    else:
        stop_event.set()


def on_message(_client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage):
    payload = msg.payload.decode("utf-8", errors="replace")
    print(f"message topic={msg.topic} payload={payload}")
    received.append(payload)
    if len(received) >= MESSAGE_LIMIT:
        stop_event.set()


def on_disconnect(_client: mqtt.Client, _userdata, rc):
    print(f"on_disconnect rc={rc}")


def main() -> int:
    client_id = f"zara-subscriber-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set()
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    def handle_signal(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"connecting host={HOST} port={PORT} topic={TOPIC} client_id={client_id}")
    try:
        client.connect(HOST, PORT, keepalive=30)
    except Exception as exc:
        print(f"connect failed: {exc}")
        return 1

    client.loop_start()
    start = time.time()
    while not stop_event.is_set() and (time.time() - start) < TIMEOUT_S:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    print(f"received_count={len(received)}")
    return 0 if received else 2


if __name__ == "__main__":
    raise SystemExit(main())

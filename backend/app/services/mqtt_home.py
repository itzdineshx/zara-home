from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from app.config import Settings


logger = logging.getLogger(__name__)


class MQTTHomeAutomationController:
    """MQTT bridge between backend voice intents and home automation hardware."""

    SUPPORTED_ACTIONS: set[str] = {
        "light_on",
        "light_off",
        "fan_on",
        "fan_off",
        "fan_speed_up",
        "fan_speed_down",
        "ac_on",
        "ac_off",
        "ac_temp_up",
        "ac_temp_down",
        "tv_on",
        "tv_off",
        "curtain_open",
        "curtain_close",
        "door_lock",
        "door_unlock",
        "all_on",
        "all_off",
        "scene_good_morning",
        "scene_good_night",
        "scene_away",
        "scene_home",
        "status_check",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connected = False
        self._loop_started = False
        self._state_lock = threading.Lock()
        self._connection_lock = threading.Lock()

        self._lights_on = False
        self._fan_on = False
        self._fan_speed = settings.home_fan_speed_min
        self._ac_on = False
        self._ac_temperature = settings.home_temperature_default
        self._tv_on = False
        self._curtains_open = False
        self._door_locked = True

        self._last_status: dict[str, Any] | None = None
        self._last_status_at: dt.datetime | None = None

        import uuid
        base_client_id = settings.home_mqtt_client_id or "zara-backend"
        unique_client_id = f"{base_client_id}-{uuid.uuid4().hex[:6]}"
        
        client_kwargs: dict[str, Any] = {
            "client_id": unique_client_id,
            "protocol": mqtt.MQTTv311,
            "transport": "tcp",
        }

        # paho-mqtt >=2.0 requires an explicit callback API version for legacy callback signatures.
        if hasattr(mqtt, "CallbackAPIVersion"):
            client_kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION1

        self._client = mqtt.Client(**client_kwargs)

        if settings.home_mqtt_username:
            self._client.username_pw_set(
                username=settings.home_mqtt_username,
                password=settings.home_mqtt_password or None,
            )

        if settings.home_mqtt_tls_enabled:
            self._configure_tls()

        retry_delay_s = max(0.05, settings.home_mqtt_retry_delay_ms / 1000.0)
        self._client.reconnect_delay_set(min_delay=retry_delay_s, max_delay=max(1.0, retry_delay_s * 10))

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_log = self._on_log

    def _configure_tls(self) -> None:
        ca_certs = self._resolve_path(self.settings.home_mqtt_tls_ca_cert)
        
        if not ca_certs:
            try:
                import certifi
                ca_certs = certifi.where()
                logger.info("Using certifi CA bundle for MQTT TLS")
            except ImportError:
                logger.warning("certifi not found, relying on system CA certs")

        certfile = self._resolve_path(self.settings.home_mqtt_tls_certfile)
        keyfile = self._resolve_path(self.settings.home_mqtt_tls_keyfile)

        self._client.tls_set(
            ca_certs=ca_certs or None,
            certfile=certfile or None,
            keyfile=keyfile or None,
        )

        if self.settings.home_mqtt_tls_insecure:
            self._client.tls_insecure_set(True)

        logger.info("Home MQTT TLS enabled (insecure=%s)", self.settings.home_mqtt_tls_insecure)

    def _on_log(self, _client: mqtt.Client, _userdata: Any, level: int, buf: str) -> None:
        logger.info("MQTT Log: %s", buf)

    def _resolve_path(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""

        path = Path(raw).expanduser()
        if not path.exists():
            logger.warning("MQTT TLS file does not exist yet: %s", path)
        return str(path)

    def start(self) -> None:
        if not self.settings.home_mqtt_enabled:
            logger.info("Home MQTT is disabled")
            return

        with self._connection_lock:
            if self._loop_started:
                return

            self._client.connect_async(
                host=self.settings.home_mqtt_host,
                port=self.settings.home_mqtt_port,
                keepalive=max(10, self.settings.home_mqtt_keepalive_s),
            )
            self._client.loop_start()
            self._loop_started = True
            logger.info(
                "Home MQTT loop started for broker %s:%s",
                self.settings.home_mqtt_host,
                self.settings.home_mqtt_port,
            )

    def stop(self) -> None:
        with self._connection_lock:
            if not self._loop_started:
                return

            try:
                self._client.disconnect()
            except Exception:
                logger.debug("MQTT disconnect failed during shutdown", exc_info=True)
            finally:
                self._client.loop_stop()
                self._loop_started = False
                self._connected = False

    async def publish_action(self, action: str, value: int | None = None) -> dict[str, Any]:
        normalized_action = action.strip().lower()
        if normalized_action not in self.SUPPORTED_ACTIONS:
            return {
                "type": normalized_action,
                "domain": "home",
                "status": "failed",
                "error": f"Unsupported home action: {normalized_action}",
            }

        command = self._build_command(normalized_action, value)
        message = {
            **command,
            "source": "zara-backend",
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

        if not self.settings.home_mqtt_enabled:
            return {
                "type": normalized_action,
                "domain": "home",
                "status": "failed",
                "error": "Home MQTT is disabled by configuration",
            }

        # Development fallback: simulate successful publish when dev mode is enabled.
        # This helps local frontend testing when a real MQTT broker is not reachable.
        if getattr(self.settings, "home_mqtt_dev_mode", False):
            logger.info("HOME_MQTT_DEV_MODE active — simulating home action %s", normalized_action)
            # Update last status snapshot as if the device responded
            with self._state_lock:
                self._last_status = {"simulated": True, "action": command["action"], "value": command.get("value")}
                self._last_status_at = dt.datetime.now(dt.timezone.utc)

            return {
                "type": normalized_action,
                "action": command["action"],
                "value": command.get("value"),
                "domain": "home",
                "status": "executed",
                "target": f"mqtt://{self.settings.home_mqtt_host}:{self.settings.home_mqtt_port}",
                "topic": self.settings.home_mqtt_control_topic,
                "connected": False,
            }

        try:
            await asyncio.to_thread(self._publish_json, message)
            return {
                "type": normalized_action,
                "action": command["action"],
                "value": command.get("value"),
                "domain": "home",
                "status": "executed",
                "target": f"mqtt://{self.settings.home_mqtt_host}:{self.settings.home_mqtt_port}",
                "topic": self.settings.home_mqtt_control_topic,
                "connected": self._connected,
            }
        except Exception as exc:
            logger.warning("Failed to publish home action %s: %s", normalized_action, exc)
            return {
                "type": normalized_action,
                "action": command["action"],
                "value": command.get("value"),
                "domain": "home",
                "status": "failed",
                "error": str(exc),
                "target": f"mqtt://{self.settings.home_mqtt_host}:{self.settings.home_mqtt_port}",
                "topic": self.settings.home_mqtt_control_topic,
            }

    def status_snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            last_status = dict(self._last_status) if isinstance(self._last_status, dict) else self._last_status
            last_status_at = self._last_status_at.isoformat() if self._last_status_at else None

        return {
            "connected": self._connected,
            "broker": f"{self.settings.home_mqtt_host}:{self.settings.home_mqtt_port}",
            "control_topic": self.settings.home_mqtt_control_topic,
            "status_topic": self.settings.home_mqtt_status_topic,
            "last_status": last_status,
            "last_status_at": last_status_at,
        }

    def _build_command(self, action: str, value: int | None) -> dict[str, Any]:
        with self._state_lock:
            if action == "light_on":
                self._lights_on = True
                return {"action": "light_on", "value": 1}

            if action == "light_off":
                self._lights_on = False
                return {"action": "light_off", "value": 0}

            if action == "fan_on":
                self._fan_on = True
                self._fan_speed = max(self._fan_speed, 50)
                return {"action": "fan_on", "value": self._fan_speed}

            if action == "fan_off":
                self._fan_on = False
                self._fan_speed = self.settings.home_fan_speed_min
                return {"action": "fan_off", "value": 0}

            if action == "fan_speed_up":
                self._fan_on = True
                next_value = self._fan_speed + max(1, self.settings.home_fan_speed_step)
                self._fan_speed = self._clamp_home_percent(next_value)
                return {"action": "fan_speed_up", "value": self._fan_speed}

            if action == "fan_speed_down":
                next_value = self._fan_speed - max(1, self.settings.home_fan_speed_step)
                self._fan_speed = self._clamp_home_percent(next_value)
                self._fan_on = self._fan_speed > 0
                return {"action": "fan_speed_down", "value": self._fan_speed}

            if action == "ac_on":
                self._ac_on = True
                return {"action": "ac_on", "value": self._ac_temperature}

            if action == "ac_off":
                self._ac_on = False
                return {"action": "ac_off", "value": 0}

            if action == "ac_temp_up":
                self._ac_on = True
                self._ac_temperature = self._clamp_temperature(self._ac_temperature + max(1, self.settings.home_ac_temp_step))
                return {"action": "ac_temp_up", "value": self._ac_temperature}

            if action == "ac_temp_down":
                self._ac_on = True
                self._ac_temperature = self._clamp_temperature(self._ac_temperature - max(1, self.settings.home_ac_temp_step))
                return {"action": "ac_temp_down", "value": self._ac_temperature}

            if action == "tv_on":
                self._tv_on = True
                return {"action": "tv_on", "value": 1}

            if action == "tv_off":
                self._tv_on = False
                return {"action": "tv_off", "value": 0}

            if action == "curtain_open":
                self._curtains_open = True
                return {"action": "curtain_open", "value": 1}

            if action == "curtain_close":
                self._curtains_open = False
                return {"action": "curtain_close", "value": 0}

            if action == "door_lock":
                self._door_locked = True
                return {"action": "door_lock", "value": 1}

            if action == "door_unlock":
                self._door_locked = False
                return {"action": "door_unlock", "value": 0}

            if action == "all_on":
                self._lights_on = True
                self._fan_on = True
                self._ac_on = True
                self._tv_on = True
                return {"action": "all_on", "value": 1}

            if action == "all_off":
                self._lights_on = False
                self._fan_on = False
                self._fan_speed = self.settings.home_fan_speed_min
                self._ac_on = False
                self._tv_on = False
                return {"action": "all_off", "value": 0}

            if action == "scene_good_morning":
                self._lights_on = True
                self._curtains_open = True
                self._fan_on = True
                self._fan_speed = max(self._fan_speed, 40)
                return {"action": "scene_good_morning", "value": 1}

            if action == "scene_good_night":
                self._lights_on = False
                self._fan_on = True
                self._fan_speed = min(35, self.settings.home_fan_speed_max)
                self._tv_on = False
                self._curtains_open = False
                self._door_locked = True
                return {"action": "scene_good_night", "value": 1}

            if action == "scene_away":
                self._lights_on = False
                self._fan_on = False
                self._fan_speed = self.settings.home_fan_speed_min
                self._ac_on = False
                self._tv_on = False
                self._curtains_open = False
                self._door_locked = True
                return {"action": "scene_away", "value": 1}

            if action == "scene_home":
                self._lights_on = True
                self._curtains_open = False
                return {"action": "scene_home", "value": 1}

            if action == "status_check":
                return {
                    "action": "status_check",
                    "value": 1,
                    "lights_on": self._lights_on,
                    "fan_on": self._fan_on,
                    "fan_speed": self._fan_speed,
                    "ac_on": self._ac_on,
                    "ac_temperature": self._ac_temperature,
                    "tv_on": self._tv_on,
                    "curtains_open": self._curtains_open,
                    "door_locked": self._door_locked,
                }

            return {"action": action}

    def _publish_json(self, payload: dict[str, Any]) -> None:
        if not self._loop_started:
            self.start()

        if not self._connected:
            self._retry_connection()

        qos = min(2, max(0, self.settings.home_mqtt_qos))
        encoded_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        result = self._client.publish(self.settings.home_mqtt_control_topic, encoded_payload, qos=qos, retain=False)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with code {result.rc}")

        result.wait_for_publish(timeout=max(0.2, self.settings.home_mqtt_publish_timeout_s))
        if not result.is_published():
            raise RuntimeError("MQTT publish timed out")

    def _retry_connection(self) -> None:
        attempts = max(1, self.settings.home_mqtt_retry_attempts)
        retry_delay_s = max(0.05, self.settings.home_mqtt_retry_delay_ms / 1000.0)

        for attempt in range(1, attempts + 1):
            if self._connected:
                return

            try:
                self._client.reconnect()
            except Exception as exc:
                logger.debug("MQTT reconnect attempt %s failed: %s", attempt, exc)

            deadline = time.monotonic() + max(0.2, self.settings.home_mqtt_publish_timeout_s)
            while time.monotonic() < deadline:
                if self._connected:
                    return
                time.sleep(0.03)

            if attempt < attempts:
                time.sleep(retry_delay_s)

        raise RuntimeError("Unable to connect to MQTT broker after retries")

    def _clamp_home_percent(self, value: int) -> int:
        minimum = min(self.settings.home_fan_speed_min, self.settings.home_fan_speed_max)
        maximum = max(self.settings.home_fan_speed_min, self.settings.home_fan_speed_max)
        return max(minimum, min(maximum, int(value)))

    def _clamp_temperature(self, value: int) -> int:
        minimum = min(self.settings.home_ac_temp_min, self.settings.home_ac_temp_max)
        maximum = max(self.settings.home_ac_temp_min, self.settings.home_ac_temp_max)
        return max(minimum, min(maximum, int(value)))

    def _on_connect(self, _client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any) -> None:
        try:
            code = int(reason_code)
        except Exception:
            code = 1

        self._connected = code == 0

        if self._connected:
            qos = min(2, max(0, self.settings.home_mqtt_qos))
            self._client.subscribe(self.settings.home_mqtt_status_topic, qos=qos)
            logger.info("Connected to MQTT broker and subscribed to %s", self.settings.home_mqtt_status_topic)
        else:
            logger.warning("MQTT connection failed with reason code=%s", reason_code)

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, reason_code: Any) -> None:
        self._connected = False
        logger.warning("Disconnected from MQTT broker (reason=%s)", reason_code)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        raw = message.payload.decode("utf-8", errors="ignore").strip()
        parsed: dict[str, Any]

        try:
            payload = json.loads(raw) if raw else {}
            if isinstance(payload, dict):
                parsed = payload
            else:
                parsed = {"message": payload}
        except json.JSONDecodeError:
            parsed = {"message": raw}

        parsed.setdefault("topic", message.topic)

        with self._state_lock:
            self._last_status = parsed
            self._last_status_at = dt.datetime.now(dt.timezone.utc)

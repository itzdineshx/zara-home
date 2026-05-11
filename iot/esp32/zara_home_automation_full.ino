#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

// WiFi credentials
const char* WIFI_SSID = "Zayma";
const char* WIFI_PASSWORD = "reddragon";

// MQTT broker (HiveMQ Cloud)
const char* MQTT_HOST = "e5c35c674acb4ec6bdb8514fa465cfa6.s1.eu.hivemq.cloud";
const uint16_t MQTT_PORT = 8883;
const char* MQTT_USER = "Zayma";
const char* MQTT_PASSWORD = "Reddragon123";
const char* TOPIC_CONTROL = "zara/home/control";
const char* TOPIC_STATUS = "zara/home/status";

// TLS options (set MQTT_USE_TLS=true for port 8883 brokers)
const bool MQTT_USE_TLS = false;
const char* MQTT_ROOT_CA = "";

// Device pins (update for your relay board and wiring)
constexpr uint8_t PIN_LIGHT = 2;
constexpr uint8_t PIN_FAN = 4;
constexpr uint8_t PIN_AC = 5;
constexpr uint8_t PIN_TV = 18;

// PWM channels for fan and AC intensity/speed simulation
constexpr uint8_t FAN_PWM_CHANNEL = 0;
constexpr uint8_t AC_PWM_CHANNEL = 1;
constexpr uint16_t PWM_FREQ = 5000;
constexpr uint8_t PWM_BITS = 8;
constexpr uint8_t PWM_MAX = 255;

// Optional servos
constexpr uint8_t PIN_CURTAIN_SERVO = 19;
constexpr uint8_t PIN_DOOR_SERVO = 21;
constexpr int CURTAIN_OPEN_ANGLE = 170;
constexpr int CURTAIN_CLOSE_ANGLE = 10;
constexpr int DOOR_LOCK_ANGLE = 170;
constexpr int DOOR_UNLOCK_ANGLE = 10;

WiFiClient wifiClient;
WiFiClientSecure secureClient;
PubSubClient mqttClient;
Servo curtainServo;
Servo doorServo;

bool wifiLogged = false;
bool mqttLogged = false;
char mqttClientId[40] = {0};
unsigned long lastWifiAttemptMs = 0;
unsigned long lastMqttAttemptMs = 0;

// State
bool lightOn = false;
bool fanOn = false;
bool acOn = false;
bool tvOn = false;
bool curtainsOpen = false;
bool doorLocked = true;
int fanLevel = 0;       // 0..255
int acLevel = 0;        // 0..255 (cooling intensity proxy)
int acTempC = 24;       // logical temperature state

int clamp255(int value) {
  if (value < 0) {
    return 0;
  }
  if (value > 255) {
    return 255;
  }
  return value;
}

int clampTemp(int value) {
  if (value < 16) {
    return 16;
  }
  if (value > 30) {
    return 30;
  }
  return value;
}

void applyFanPwm() {
  const int duty = fanOn ? fanLevel : 0;
  ledcWrite(PIN_FAN, duty);
}

void applyAcPwm() {
  const int duty = acOn ? acLevel : 0;
  ledcWrite(PIN_AC, duty);
}

void applyDigitalOutputs() {
  digitalWrite(PIN_LIGHT, lightOn ? HIGH : LOW);
  digitalWrite(PIN_FAN, fanOn ? HIGH : LOW);
  digitalWrite(PIN_AC, acOn ? HIGH : LOW);
  digitalWrite(PIN_TV, tvOn ? HIGH : LOW);

  applyFanPwm();
  applyAcPwm();

  curtainServo.write(curtainsOpen ? CURTAIN_OPEN_ANGLE : CURTAIN_CLOSE_ANGLE);
  doorServo.write(doorLocked ? DOOR_LOCK_ANGLE : DOOR_UNLOCK_ANGLE);
}

void publishStatus(const char* status) {
  JsonDocument doc;
  doc["status"] = status;
  doc["light_on"] = lightOn;
  doc["fan_on"] = fanOn;
  doc["fan_level"] = fanLevel;
  doc["ac_on"] = acOn;
  doc["ac_level"] = acLevel;
  doc["ac_temp_c"] = acTempC;
  doc["tv_on"] = tvOn;
  doc["curtains_open"] = curtainsOpen;
  doc["door_locked"] = doorLocked;
  doc["uptime_ms"] = millis();

  char payload[512];
  size_t len = serializeJson(doc, payload, sizeof(payload));
  mqttClient.publish(TOPIC_STATUS, reinterpret_cast<const uint8_t*>(payload), static_cast<unsigned int>(len), false);
}

void applyAction(const String& action, int value) {
  if (action == "light_on") {
    lightOn = true;
    applyDigitalOutputs();
    publishStatus("light_on");
    return;
  }

  if (action == "light_off") {
    lightOn = false;
    applyDigitalOutputs();
    publishStatus("light_off");
    return;
  }

  if (action == "fan_on") {
    fanOn = true;
    if (value >= 0) {
      fanLevel = clamp255(value);
    }
    if (fanLevel == 0) {
      fanLevel = 120;
    }
    applyDigitalOutputs();
    publishStatus("fan_on");
    return;
  }

  if (action == "fan_off") {
    fanOn = false;
    fanLevel = 0;
    applyDigitalOutputs();
    publishStatus("fan_off");
    return;
  }

  if (action == "fan_speed_up") {
    fanOn = true;
    if (value >= 0) {
      fanLevel = clamp255(value);
    } else {
      fanLevel = clamp255(fanLevel + 25);
    }
    applyDigitalOutputs();
    publishStatus("fan_speed_up");
    return;
  }

  if (action == "fan_speed_down") {
    if (value >= 0) {
      fanLevel = clamp255(value);
    } else {
      fanLevel = clamp255(fanLevel - 25);
    }
    fanOn = fanLevel > 0;
    applyDigitalOutputs();
    publishStatus("fan_speed_down");
    return;
  }

  if (action == "ac_on") {
    acOn = true;
    if (value >= 16 && value <= 30) {
      acTempC = value;
    }
    if (acLevel == 0) {
      acLevel = 150;
    }
    applyDigitalOutputs();
    publishStatus("ac_on");
    return;
  }

  if (action == "ac_off") {
    acOn = false;
    acLevel = 0;
    applyDigitalOutputs();
    publishStatus("ac_off");
    return;
  }

  if (action == "ac_temp_up") {
    acOn = true;
    if (value >= 16 && value <= 30) {
      acTempC = value;
    } else {
      acTempC = clampTemp(acTempC + 1);
    }
    applyDigitalOutputs();
    publishStatus("ac_temp_up");
    return;
  }

  if (action == "ac_temp_down") {
    acOn = true;
    if (value >= 16 && value <= 30) {
      acTempC = value;
    } else {
      acTempC = clampTemp(acTempC - 1);
    }
    applyDigitalOutputs();
    publishStatus("ac_temp_down");
    return;
  }

  if (action == "tv_on") {
    tvOn = true;
    applyDigitalOutputs();
    publishStatus("tv_on");
    return;
  }

  if (action == "tv_off") {
    tvOn = false;
    applyDigitalOutputs();
    publishStatus("tv_off");
    return;
  }

  if (action == "curtain_open") {
    curtainsOpen = true;
    applyDigitalOutputs();
    publishStatus("curtain_open");
    return;
  }

  if (action == "curtain_close") {
    curtainsOpen = false;
    applyDigitalOutputs();
    publishStatus("curtain_close");
    return;
  }

  if (action == "door_lock") {
    doorLocked = true;
    applyDigitalOutputs();
    publishStatus("door_lock");
    return;
  }

  if (action == "door_unlock") {
    doorLocked = false;
    applyDigitalOutputs();
    publishStatus("door_unlock");
    return;
  }

  if (action == "all_on") {
    lightOn = true;
    fanOn = true;
    acOn = true;
    tvOn = true;
    curtainsOpen = true;
    doorLocked = false;
    if (fanLevel == 0) {
      fanLevel = 120;
    }
    if (acLevel == 0) {
      acLevel = 150;
    }
    applyDigitalOutputs();
    publishStatus("all_on");
    return;
  }

  if (action == "all_off") {
    lightOn = false;
    fanOn = false;
    acOn = false;
    tvOn = false;
    curtainsOpen = false;
    doorLocked = true;
    fanLevel = 0;
    acLevel = 0;
    applyDigitalOutputs();
    publishStatus("all_off");
    return;
  }

  if (action == "scene_good_morning") {
    lightOn = true;
    fanOn = true;
    fanLevel = 110;
    acOn = false;
    tvOn = false;
    curtainsOpen = true;
    doorLocked = false;
    applyDigitalOutputs();
    publishStatus("scene_good_morning");
    return;
  }

  if (action == "scene_good_night") {
    lightOn = false;
    fanOn = true;
    fanLevel = 80;
    acOn = false;
    tvOn = false;
    curtainsOpen = false;
    doorLocked = true;
    applyDigitalOutputs();
    publishStatus("scene_good_night");
    return;
  }

  if (action == "scene_away") {
    lightOn = false;
    fanOn = false;
    acOn = false;
    tvOn = false;
    curtainsOpen = false;
    doorLocked = true;
    fanLevel = 0;
    acLevel = 0;
    applyDigitalOutputs();
    publishStatus("scene_away");
    return;
  }

  if (action == "scene_home") {
    lightOn = true;
    fanOn = true;
    fanLevel = 120;
    acOn = true;
    acLevel = 150;
    tvOn = true;
    curtainsOpen = true;
    doorLocked = false;
    applyDigitalOutputs();
    publishStatus("scene_home");
    return;
  }

  if (action == "status_check") {
    publishStatus("status_check");
    return;
  }

  publishStatus("unknown_action");
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String incomingTopic = String(topic);
  if (incomingTopic != TOPIC_CONTROL) {
    return;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    publishStatus("bad_json");
    return;
  }

  const char* actionRaw = doc["action"] | "";
  int value = doc["value"].is<int>() ? doc["value"].as<int>() : -1;

  String action = String(actionRaw);
  action.trim();
  action.toLowerCase();

  if (action.length() == 0) {
    publishStatus("missing_action");
    return;
  }

  Serial.printf("[MQTT] action=%s value=%d\n", action.c_str(), value);
  applyAction(action, value);
}

void connectWifiIfNeeded() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiLogged) {
      Serial.print("[WIFI] Connected, IP: ");
      Serial.println(WiFi.localIP());
      wifiLogged = true;
    }
    return;
  }

  const unsigned long now = millis();
  if (now - lastWifiAttemptMs < 3000) {
    return;
  }

  lastWifiAttemptMs = now;
  wifiLogged = false;
  Serial.printf("[WIFI] Connecting to %s...\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void connectMqttIfNeeded() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (mqttClient.connected()) {
    if (!mqttLogged) {
      Serial.println("[MQTT] Connected.");
      mqttLogged = true;
      mqttClient.subscribe(TOPIC_CONTROL);
      publishStatus("online");
    }
    return;
  }

  const unsigned long now = millis();
  if (now - lastMqttAttemptMs < 3000) {
    return;
  }

  lastMqttAttemptMs = now;
  mqttLogged = false;

  snprintf(mqttClientId, sizeof(mqttClientId), "zara-home-%lu", static_cast<unsigned long>(esp_random()));

  Serial.printf("[MQTT] Connecting to %s:%u...\n", MQTT_HOST, MQTT_PORT);
  bool ok;
  if (strlen(MQTT_USER) > 0) {
    ok = mqttClient.connect(mqttClientId, MQTT_USER, MQTT_PASSWORD);
  } else {
    ok = mqttClient.connect(mqttClientId);
  }

  if (!ok) {
    Serial.printf("[MQTT] Connect failed rc=%d\n", mqttClient.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(250);
  Serial.println("[BOOT] ZARA Home Automation Full Controller starting...");

  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_AC, OUTPUT);
  pinMode(PIN_TV, OUTPUT);

  ledcAttach(PIN_FAN, PWM_FREQ, PWM_BITS);
  ledcAttach(PIN_AC, PWM_FREQ, PWM_BITS);

  curtainServo.setPeriodHertz(50);
  doorServo.setPeriodHertz(50);
  curtainServo.attach(PIN_CURTAIN_SERVO, 500, 2400);
  doorServo.attach(PIN_DOOR_SERVO, 500, 2400);

  applyDigitalOutputs();

  if (MQTT_USE_TLS) {
    if (strlen(MQTT_ROOT_CA) > 0) {
      secureClient.setCACert(MQTT_ROOT_CA);
    } else {
      secureClient.setInsecure();
    }
    mqttClient.setClient(secureClient);
  } else {
    mqttClient.setClient(wifiClient);
  }

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  connectWifiIfNeeded();
  connectMqttIfNeeded();

  if (mqttClient.connected()) {
    mqttClient.loop();
  }
}

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip().strip("\"'").rstrip("/") for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    """
    ZARA configuration settings with production-grade AI routing.
    
    AI Architecture:
    - Primary (online): Gemini Flash 2.0 via OpenRouter (fastest cloud AI)
    - Fallback (local): Gemma E2B via Ollama (reliable local inference)
    - Fallback (secondary): Secondary local model for non-English or large contexts
    
    The router tries online first for best quality and speed, falls back to local
    on cloud timeout/error for resilience, and can run offline-only mode for testing.
    """
    app_name: str = os.getenv("APP_NAME", "ZARA AI Backend")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")

    default_mode: str = os.getenv("DEFAULT_MODE", "smart")

    # OpenRouter: Gemini Flash 2.0 (primary cloud AI)
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")  # Gemini Flash 2.0
    openrouter_timeout_s: float = _env_float("OPENROUTER_TIMEOUT_S", 10.0)
    openrouter_temperature: float = _env_float("OPENROUTER_TEMPERATURE", 0.65)
    openrouter_max_tokens: int = _env_int("OPENROUTER_MAX_TOKENS", 720)

    # Ollama: Local inference for fallback (when cloud unavailable)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma2:2b")  # Gemma E2B (primary local fallback)
    ollama_fallback_model: str = os.getenv("OLLAMA_FALLBACK_MODEL", "gemma2:2b")  # Secondary local model
    ollama_timeout_s: float = _env_float("OLLAMA_TIMEOUT_S", 8.0)
    ollama_num_ctx: int = _env_int("OLLAMA_NUM_CTX", 2048)
    ollama_num_predict: int = _env_int("OLLAMA_NUM_PREDICT", 260)

    whisper_model_size: str = os.getenv("WHISPER_MODEL_SIZE", "tiny")
    whisper_multilingual_model_size: str = os.getenv("WHISPER_MULTILINGUAL_MODEL_SIZE", "base")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    max_audio_seconds: int = _env_int("MAX_AUDIO_SECONDS", 8)

    cache_ttl_seconds: int = _env_int("CACHE_TTL_SECONDS", 90)
    cache_max_entries: int = _env_int("CACHE_MAX_ENTRIES", 256)

    memory_limit: int = _env_int("MEMORY_LIMIT", 12)

    automation_execute: bool = _env_bool("AUTOMATION_EXECUTE", False)
    home_automation_default: bool = _env_bool("HOME_AUTOMATION_DEFAULT", False)

    home_mqtt_enabled: bool = _env_bool("HOME_MQTT_ENABLED", True)
    home_mqtt_host: str = os.getenv("HOME_MQTT_HOST", "127.0.0.1")
    home_mqtt_port: int = _env_int("HOME_MQTT_PORT", 1883)
    home_mqtt_keepalive_s: int = _env_int("HOME_MQTT_KEEPALIVE_S", 30)
    home_mqtt_client_id: str = os.getenv("HOME_MQTT_CLIENT_ID", "zara-backend")
    home_mqtt_username: str = os.getenv("HOME_MQTT_USERNAME", "")
    home_mqtt_password: str = os.getenv("HOME_MQTT_PASSWORD", "")
    home_mqtt_tls_enabled: bool = _env_bool("HOME_MQTT_TLS_ENABLED", False)
    home_mqtt_tls_insecure: bool = _env_bool("HOME_MQTT_TLS_INSECURE", False)
    home_mqtt_tls_ca_cert: str = os.getenv("HOME_MQTT_TLS_CA_CERT", "")
    home_mqtt_tls_certfile: str = os.getenv("HOME_MQTT_TLS_CERTFILE", "")
    home_mqtt_tls_keyfile: str = os.getenv("HOME_MQTT_TLS_KEYFILE", "")
    home_mqtt_control_topic: str = os.getenv("HOME_MQTT_CONTROL_TOPIC", "zara/home/control")
    home_mqtt_status_topic: str = os.getenv("HOME_MQTT_STATUS_TOPIC", "zara/home/status")
    home_mqtt_qos: int = _env_int("HOME_MQTT_QOS", 1)
    home_mqtt_retry_attempts: int = _env_int("HOME_MQTT_RETRY_ATTEMPTS", 3)
    home_mqtt_retry_delay_ms: int = _env_int("HOME_MQTT_RETRY_DELAY_MS", 250)
    home_mqtt_publish_timeout_s: float = _env_float("HOME_MQTT_PUBLISH_TIMEOUT_S", 1.5)

    # Development fallback: when true, MQTT publishes are simulated locally
    # This allows dashboard toggles to behave as executed without a real broker.
    home_mqtt_dev_mode: bool = _env_bool("HOME_MQTT_DEV_MODE", False)
    home_temperature_default: int = _env_int("HOME_TEMPERATURE_DEFAULT", 24)
    home_fan_speed_step: int = _env_int("HOME_FAN_SPEED_STEP", 10)
    home_fan_speed_min: int = _env_int("HOME_FAN_SPEED_MIN", 0)
    home_fan_speed_max: int = _env_int("HOME_FAN_SPEED_MAX", 100)
    home_ac_temp_step: int = _env_int("HOME_AC_TEMP_STEP", 1)
    home_ac_temp_min: int = _env_int("HOME_AC_TEMP_MIN", 16)
    home_ac_temp_max: int = _env_int("HOME_AC_TEMP_MAX", 30)

    mcp_enabled: bool = _env_bool("MCP_ENABLED", False)
    mcp_transport: str = os.getenv("MCP_TRANSPORT", "http")
    mcp_http_url: str = os.getenv("MCP_HTTP_URL", "http://127.0.0.1:8099/mcp")
    mcp_ws_url: str = os.getenv("MCP_WS_URL", "ws://127.0.0.1:8099/mcp")
    mcp_stdio_command: str = os.getenv("MCP_STDIO_COMMAND", "")
    mcp_auth_mode: str = os.getenv("MCP_AUTH_MODE", "none")
    mcp_auth_header: str = os.getenv("MCP_AUTH_HEADER", "Authorization")
    mcp_auth_token: str = os.getenv("MCP_AUTH_TOKEN", "")
    mcp_timeout_s: float = _env_float("MCP_TIMEOUT_S", 8.0)
    mcp_open_url_tool: str = os.getenv("MCP_OPEN_URL_TOOL", "open_url")

    tts_enabled: bool = _env_bool("TTS_ENABLED", False)
    tts_model_name: str = os.getenv("TTS_MODEL_NAME", "tts_models/en/ljspeech/tacotron2-DDC_ph")

    cors_origins: list[str] = field(
        default_factory=lambda: _env_csv(
            "CORS_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080,http://localhost:8081,http://127.0.0.1:8081,http://localhost:5173,http://127.0.0.1:5173",
        ),
    )


settings = Settings()

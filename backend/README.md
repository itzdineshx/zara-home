# ZARA AI Lightweight Backend

FastAPI backend optimized for low-resource servers (2-4 GB RAM) with async routing, lightweight voice processing, and safe automation.

## Core Stack

- FastAPI (async)
- OpenRouter (Gemini Flash 2.0 primary)
- Ollama (phi3:mini or gemma2:2b fallback)
- Faster-Whisper (lazy loaded)
- Coqui TTS (optional, lazy loaded)
- Uvicorn + Gunicorn

## Why This Is Lightweight

- Async I/O for all network paths (OpenRouter/Ollama/WebSocket)
- Lazy model loading (Whisper and TTS load only when needed)
- Short in-memory context only (last 5 messages)
- TTL response cache to reduce repeated LLM calls
- GZip-compressed JSON responses
- Rule-based automation only (no shell command execution)

## API Endpoints

- POST /chat
- POST /voice
- POST /mode
- POST /home-mode
- GET /home-mode
- GET /home/status
- WebSocket /ws/orb
- GET /health

### Response Format

All main AI responses follow:

{
  "text": "...",
  "emotion": "neutral",
  "audio_features": {
    "volume": 0.5,
    "pitch": 200
  },
  "action": null
}

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

   pip install -r backend/requirements.txt

  Optional Coqui TTS (only on Python 3.9-3.11):

  pip install -r backend/requirements-tts.txt

3. Copy environment template:

   copy backend/.env.example backend/.env

4. Set OPENROUTER_API_KEY in backend/.env.
5. Start API:

   uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

## Production Run (Gunicorn + UvicornWorker)

gunicorn -c backend/gunicorn_conf.py app.main:app --chdir backend

Render build command recommendation:

pip install -r backend/requirements-render.txt

Render start command must point at the actual FastAPI app, not the default placeholder. For buildpacks, the backend also includes `backend/Procfile` with:

web: gunicorn -c gunicorn_conf.py app.main:app

## Docker

Build:

docker build -t zara-backend -f backend/Dockerfile .

Run:

docker run --env-file backend/.env -p 8000:8000 zara-backend

## Mode Routing Logic

- online: OpenRouter primary, offline fallback on timeout/failure.
- offline: Ollama only, no cloud fallback.
- smart:
  - short/simple requests -> Ollama first
  - complex requests -> OpenRouter first
  - timeout/failure -> automatic fallback to alternate path

## Voice Pipeline

- Receives short audio chunks (2-5 seconds recommended)
- Extracts lightweight features (volume, pitch, speech rate)
- Transcribes with Faster-Whisper tiny/base
- Routes text through AI router
- Returns compact response payload

## Safe Automation

Supported actions:

- open youtube
- search queries
- get current time/date
- home automation commands over MQTT (when Home Automation is enabled)

Dangerous OS command execution is intentionally not implemented.

## Home Automation (ESP32 + MQTT)

The backend now supports smart-device control via MQTT using a dedicated Home Automation gate.

- Commands are only published when Home Automation is ON.
- Control topic: `zara/home/control`
- Status topic: `zara/home/status`

Full setup guide and payload details:

- See `backend/HOME_AUTOMATION_MQTT.md`

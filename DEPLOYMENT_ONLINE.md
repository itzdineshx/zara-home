# ZARA AI Online Hosting (Frontend + Backend + Home Automation)

This guide deploys ZARA AI to a VPS with HTTPS and online home automation control.

## What You Get

- Public frontend over HTTPS
- Public backend API over HTTPS
- MQTT bridge from backend to ESP32 for home automation commands
- Optional self-hosted Mosquitto broker

## 1) Prerequisites

- Ubuntu VPS (recommended: 2 vCPU, 4 GB RAM)
- Domain names:
  - `zara.example.com` (frontend)
  - `api.zara.example.com` (backend)
- Docker + Docker Compose plugin installed
- Open ports on VPS firewall: `80`, `443`

## 2) Clone and Prepare Environment

```bash
git clone https://github.com/itzdineshx/zara-aura.git
cd zara-aura
cp deploy/.env.online.example deploy/.env.online
cp backend/.env.example backend/.env
```

Edit `deploy/.env.online`:

- Set `FRONTEND_DOMAIN`
- Set `API_DOMAIN`
- Set `VITE_BACKEND_URL`
- Set `CORS_ORIGINS`
- Set MQTT values (`HOME_MQTT_*`)

Edit `backend/.env`:

- Set `OPENROUTER_API_KEY`
- Keep any AI model overrides you need

## 3) AI Model Configuration

ZARA uses a production-grade two-tier AI strategy: Gemini Flash 2.0 (cloud) primary, Gemma E2B (local) fallback.

### Gemini Flash 2.0 (Primary Cloud AI)

**Requirement:** OpenRouter API key

In `backend/.env`:
```
OPENROUTER_API_KEY=<your-api-key-from-openrouter.ai>
OPENROUTER_MODEL=google/gemini-2.0-flash-001
DEFAULT_MODE=smart
```

### Gemma E2B (Fallback Local AI)

**Requirement:** None (built-in), ~2GB RAM for Ollama inference

`backend/.env` (optional, defaults already set):
```
OLLAMA_MODEL=gemma2:2b
OLLAMA_BASE_URL=http://localhost:11434
```

Backend automatically falls back to Gemma E2B if cloud times out or errors.

## 4) Option A (Recommended): Managed MQTT Broker

Use a managed broker (for example HiveMQ Cloud) so both backend and ESP32 can connect from anywhere without exposing your own broker port.

In `deploy/.env.online`:

- `HOME_MQTT_HOST=<your-cloud-broker-host>`
- `HOME_MQTT_PORT=8883`
- `HOME_MQTT_USERNAME=<broker-username>`
- `HOME_MQTT_PASSWORD=<broker-password>`
- `HOME_MQTT_TLS_ENABLED=true`
- `HOME_MQTT_TLS_INSECURE=false`

Start stack:

```bash
docker compose --env-file deploy/.env.online -f docker-compose.online.yml up -d --build
```

## 5) Option B: Self-Hosted Mosquitto on the VPS

Create broker password file:

```bash
docker run --rm -it -v "$(pwd)/deploy/mosquitto:/mosquitto" eclipse-mosquitto:2 mosquitto_passwd -c /mosquitto/passwd zara
```

Set in `deploy/.env.online`:

- `HOME_MQTT_HOST=mosquitto`
- `HOME_MQTT_PORT=1883`
- `HOME_MQTT_USERNAME=zara`
- `HOME_MQTT_PASSWORD=<same-password-you-entered>`
- `HOME_MQTT_TLS_ENABLED=false`

Start stack with MQTT profile:

```bash
docker compose --env-file deploy/.env.online -f docker-compose.online.yml --profile selfhosted-mqtt up -d --build
```

## 5) DNS Setup

Create these DNS A records pointing to your VPS public IP:

- `zara.example.com`
- `api.zara.example.com`

Caddy will automatically issue and renew TLS certificates.

## 7) ESP32 Online Home Automation Settings

Update your firmware MQTT constants to match the broker you selected:

- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USER`
- `MQTT_PASSWORD`

Keep topic names consistent with backend env:

- `zara/home/control`
- `zara/home/status`

For managed TLS brokers, use `WiFiClientSecure` in the ESP32 sketch and load the broker CA certificate.

## 7) Verify Production

Check service status:

```bash
docker compose --env-file deploy/.env.online -f docker-compose.online.yml ps
```

Backend health:

```bash
curl https://api.zara.example.com/health
```

Home automation status:

```bash
curl https://api.zara.example.com/home/status
```

## 8) Safety Recommendations (Important)

- Keep home automation default off (`HOME_AUTOMATION_DEFAULT=false`).
- Use strong MQTT credentials and rotate periodically.
- Prefer TLS MQTT for internet control.
- Never arm engine at boot on an attached propeller.
- Add a hardware kill switch for motor power.

## 9) Updates

Pull new code and redeploy:

```bash
git pull
docker compose --env-file deploy/.env.online -f docker-compose.online.yml up -d --build
```

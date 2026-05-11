from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response

from app.config import settings
from app.schemas import (
    AudioFeatures,
    ChatRequest,
    ChatResponse,
    HomeModeRequest,
    HomeModeResponse,
    HomeStatusResponse,
    ModeLiteral,
    ModeRequest,
    ModeResponse,
    TTSRequest,
    VoiceResponse,
)
from app.services.ai_router import AIRouterService
from app.services.audio_features import AudioFeatureResult, AudioFeatureService
from app.services.automation import AutomationEngine
from app.services.emotion_service import EmotionService
from app.services.language_service import LanguageDetectionResult, LanguageService
from app.services.memory import MemoryStore
from app.services.mcp_service import MCPService
from app.services.mode_state import ModeState
from app.services.mqtt_home import MQTTHomeAutomationController
from app.services.ollama_client import OllamaClient
from app.services.openrouter_client import OpenRouterClient
from app.services.tts_service import TTSService
from app.services.whisper_service import TranscriptionResult, WhisperService


logger = logging.getLogger(__name__)


_SUPPORTED_RESPONSE_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ta": "Tamil",
}


def _normalize_preferred_language(language: str | None) -> str | None:
    if not language:
        return None

    lowered = language.strip().lower()
    aliases = {
        "en": "en",
        "en-us": "en",
        "en-gb": "en",
        "english": "en",
        "ta": "ta",
        "ta-in": "ta",
        "tamil": "ta",
    }

    normalized = aliases.get(lowered, lowered)
    return normalized if normalized in _SUPPORTED_RESPONSE_LANGUAGE_NAMES else None


def _resolve_response_language(
    detected: LanguageDetectionResult,
    preferred_code: str | None,
) -> LanguageDetectionResult:
    if not preferred_code:
        if detected.code == "ta":
            return detected
        return LanguageDetectionResult(
            code="en",
            name=_SUPPORTED_RESPONSE_LANGUAGE_NAMES["en"],
            confidence=max(0.8, detected.confidence),
        )

    # Honor explicit Tamil preference for reply language.
    if preferred_code == "ta":
        return LanguageDetectionResult(
            code=preferred_code,
            name=_SUPPORTED_RESPONSE_LANGUAGE_NAMES[preferred_code],
            confidence=max(0.8, detected.confidence),
        )

    # When UI is set to English, still allow strong Tamil detections.
    if detected.code == "ta" and detected.confidence >= 0.7:
        return detected

    return LanguageDetectionResult(
        code="en",
        name=_SUPPORTED_RESPONSE_LANGUAGE_NAMES["en"],
        confidence=max(0.8, detected.confidence),
    )


def _merge_voice_language_detection(
    text_detected: LanguageDetectionResult,
    transcription: TranscriptionResult,
) -> LanguageDetectionResult:
    whisper_code = _normalize_preferred_language(transcription.language_code)
    if not whisper_code:
        return text_detected

    if whisper_code == text_detected.code:
        return LanguageDetectionResult(
            code=text_detected.code,
            name=text_detected.name,
            confidence=max(text_detected.confidence, transcription.language_confidence),
        )

    # Prefer Whisper-detected language when text-based detection is uncertain or falls back to English.
    if transcription.language_confidence >= 0.55 and (text_detected.code == "en" or text_detected.confidence < 0.74):
        return LanguageDetectionResult(
            code=whisper_code,
            name=_SUPPORTED_RESPONSE_LANGUAGE_NAMES[whisper_code],
            confidence=max(text_detected.confidence, transcription.language_confidence),
        )

    return text_detected


def _is_browser_action(action: dict[str, object] | None) -> bool:
    if not action:
        return False

    action_type = str(action.get("type") or "").strip().lower()
    return action_type in {
        "spotify_play",
        "spotify_music",
        "open_spotify",
        "youtube_play",
        "open_youtube",
        "open_maps",
        "open_gmail",
        "open_github",
        "open_google",
        "open_website",
        "web_search",
    }


def _is_home_action(action: dict[str, object] | None) -> bool:
    if not action:
        return False

    return str(action.get("domain") or "").strip().lower() == "home"


def _build_home_action_response(action: dict[str, object], language_code: str) -> str:
    command = str(action.get("action") or action.get("type") or "home_command").replace("_", " ").strip()
    status = str(action.get("status") or "planned").strip().lower()
    detail = str(action.get("detail") or "").strip()
    error = str(action.get("error") or "").strip()

    if language_code == "hi":
        if status == "blocked_home_mode":
            return "होम ऑटोमेशन बंद है। डिवाइस कमांड भेजने के लिए सेटिंग्स में इसे चालू करें।"
        if status == "executed":
            return f"ठीक है, {command} कमांड होम सिस्टम को भेज दिया गया है।"
        if status == "failed":
            return f"{command} कमांड नहीं भेज सका: {error or 'MQTT कनेक्शन जांचें।'}"
        return detail or f"{command} कमांड स्थिति: {status}"

    if language_code == "ta":
        if status == "blocked_home_mode":
            return "Home Automation ஆஃப் நிலையில் உள்ளது. Device கட்டளைகளை அனுப்ப Settings-ல் அதை இயக்குங்கள்."
        if status == "executed":
            return f"சரி, {command} கட்டளை home system-க்கு அனுப்பப்பட்டது."
        if status == "failed":
            return f"{command} கட்டளையை அனுப்ப முடியவில்லை: {error or 'MQTT இணைப்பை சரிபார்க்கவும்.'}"
        return detail or f"{command} கட்டளை நிலை: {status}"

    if language_code == "te":
        if status == "blocked_home_mode":
            return "Home Automation ఆఫ్‌లో ఉంది. Device కమాండ్లు పంపడానికి Settings లో దాన్ని ఆన్ చేయండి."
        if status == "executed":
            return f"సరే, {command} కమాండ్ home system కి పంపించబడింది."
        if status == "failed":
            return f"{command} కమాండ్ పంపడం విఫలమైంది: {error or 'MQTT కనెక్షన్‌ను చెక్ చేయండి.'}"
        return detail or f"{command} కమాండ్ స్థితి: {status}"

    if language_code == "ml":
        if status == "blocked_home_mode":
            return "Home Automation ഓഫ് ആണ്. Device commandകൾ അയയ്ക്കാൻ Settings-ൽ അത് ഓൺ ചെയ്യുക."
        if status == "executed":
            return f"ശരി, {command} command home system ലേക്ക് അയച്ചു."
        if status == "failed":
            return f"{command} command അയയ്ക്കാൻ കഴിഞ്ഞില്ല: {error or 'MQTT കണക്ഷൻ പരിശോധിക്കുക.'}"
        return detail or f"{command} command status: {status}"

    if status == "blocked_home_mode":
        return "Home Automation is OFF. Enable it in settings to send device commands."
    if status == "executed":
        return f"Okay, {command} command sent to the home automation system."
    if status == "failed":
        return f"I could not send the {command} command: {error or 'Please check MQTT connectivity.'}"

    return detail or f"Home command {command} status: {status}."


def _build_browser_action_response(action: dict[str, object], language_code: str) -> str:
    action_type = str(action.get("type") or "").strip().lower()
    query = str(action.get("query") or "").strip()
    destination = str(action.get("destination") or "").strip()
    domain = str(action.get("domain") or "").strip()
    is_spotify_action = "spotify" in action_type
    is_youtube_action = "youtube" in action_type

    if language_code == "hi":
        if is_spotify_action:
            return f"ठीक है, मैं Spotify पर {query} चला रहा हूं।" if query else "ठीक है, मैं Spotify खोल रहा हूं।"
        if is_youtube_action:
            return f"ठीक है, मैं YouTube पर {query} वीडियो चला रहा हूं।" if query else "ठीक है, मैं YouTube खोल रहा हूं।"
        if action_type == "open_maps":
            return f"ठीक है, मैं {destination} के लिए मैप खोल रहा हूं।" if destination else "ठीक है, मैं Google Maps खोल रहा हूं।"
        if action_type == "open_gmail":
            return "ठीक है, मैं Gmail खोल रहा हूं।"
        if action_type == "open_github":
            return "ठीक है, मैं GitHub खोल रहा हूं।"
        if action_type == "open_google":
            return "ठीक है, मैं Google खोल रहा हूं।"
        if action_type == "open_website":
            return f"ठीक है, मैं {domain} खोल रहा हूं।" if domain else "ठीक है, वेबसाइट खोल रहा हूं।"
        if action_type == "web_search":
            return f"ठीक है, मैं {query} के लिए वेब सर्च कर रहा हूं।" if query else "ठीक है, वेब सर्च खोल रहा हूं।"
    elif language_code == "ta":
        if is_spotify_action:
            return f"சரி, Spotify-ல் {query} பாடலை இப்போது இயக்குகிறேன்." if query else "சரி, Spotify-ஐ திறக்கிறேன்."
        if is_youtube_action:
            return f"சரி, YouTube-ல் {query} வீடியோவை இப்போது இயக்குகிறேன்." if query else "சரி, YouTube-ஐ திறக்கிறேன்."
        if action_type == "open_maps":
            return f"சரி, {destination} க்கு Maps திறக்கிறேன்." if destination else "சரி, Google Maps திறக்கிறேன்."
        if action_type == "open_gmail":
            return "சரி, Gmail திறக்கிறேன்."
        if action_type == "open_github":
            return "சரி, GitHub திறக்கிறேன்."
        if action_type == "open_google":
            return "சரி, Google திறக்கிறேன்."
        if action_type == "open_website":
            return f"சரி, {domain} தளத்தை திறக்கிறேன்." if domain else "சரி, இணையதளத்தை திறக்கிறேன்."
        if action_type == "web_search":
            return f"சரி, {query} க்கு வெப் தேடல் செய்கிறேன்." if query else "சரி, வெப் தேடல் திறக்கிறேன்."
    elif language_code == "te":
        if is_spotify_action:
            return f"సరే, Spotify లో {query} ప్లే చేస్తున్నాను." if query else "సరే, Spotify ను తెరుస్తున్నాను."
        if is_youtube_action:
            return f"సరే, YouTube లో {query} వీడియో ప్లే చేస్తున్నాను." if query else "సరే, YouTube ను తెరుస్తున్నాను."
        if action_type == "open_maps":
            return f"సరే, {destination} కోసం మ్యాప్స్ తెరుస్తున్నాను." if destination else "సరే, Google Maps తెరుస్తున్నాను."
        if action_type == "open_gmail":
            return "సరే, Gmail తెరుస్తున్నాను."
        if action_type == "open_github":
            return "సరే, GitHub తెరుస్తున్నాను."
        if action_type == "open_google":
            return "సరే, Google తెరుస్తున్నాను."
        if action_type == "open_website":
            return f"సరే, {domain} వెబ్‌సైట్ తెరుస్తున్నాను." if domain else "సరే, వెబ్‌సైట్ తెరుస్తున్నాను."
        if action_type == "web_search":
            return f"సరే, {query} కోసం వెబ్ సెర్చ్ చేస్తున్నాను." if query else "సరే, వెబ్ సెర్చ్ తెరుస్తున్నాను."
    elif language_code == "ml":
        if is_spotify_action:
            return f"ശരി, Spotify-ൽ {query} ഇപ്പോൾ പ്ലേ ചെയ്യുന്നു." if query else "ശരി, Spotify തുറക്കുന്നു."
        if is_youtube_action:
            return f"ശരി, YouTube-ൽ {query} വീഡിയോ ഇപ്പോൾ പ്ലേ ചെയ്യുന്നു." if query else "ശരി, YouTube തുറക്കുന്നു."
        if action_type == "open_maps":
            return f"ശരി, {destination} ലേക്കുള്ള മാപ്പ് തുറക്കുന്നു." if destination else "ശരി, Google Maps തുറക്കുന്നു."
        if action_type == "open_gmail":
            return "ശരി, Gmail തുറക്കുന്നു."
        if action_type == "open_github":
            return "ശരി, GitHub തുറക്കുന്നു."
        if action_type == "open_google":
            return "ശരി, Google തുറക്കുന്നു."
        if action_type == "open_website":
            return f"ശരി, {domain} വെബ്സൈറ്റ് തുറക്കുന്നു." if domain else "ശരി, വെബ്സൈറ്റ് തുറക്കുന്നു."
        if action_type == "web_search":
            return f"ശരി, {query} ന് വെബ് തിരയൽ നടത്തുന്നു." if query else "ശരി, വെബ് തിരയൽ തുറക്കുന്നു."

    if is_spotify_action:
        return f"Okay, playing {query} on Spotify now." if query else "Okay, opening Spotify now."
    if is_youtube_action:
        return f"Okay, playing {query} on YouTube now." if query else "Okay, opening YouTube now."
    if action_type == "open_maps":
        return f"Okay, opening maps for {destination}." if destination else "Okay, opening Google Maps now."
    if action_type == "open_gmail":
        return "Okay, opening Gmail now."
    if action_type == "open_github":
        return "Okay, opening GitHub now."
    if action_type == "open_google":
        return "Okay, opening Google now."
    if action_type == "open_website":
        return f"Okay, opening {domain} now." if domain else "Okay, opening the website now."
    if action_type == "web_search":
        return f"Okay, searching the web for {query} now." if query else "Okay, opening web search now."

    return "Okay, executing your request now."


@dataclass(slots=True)
class ServiceContainer:
    memory_store: MemoryStore
    mode_state: ModeState
    home_controller: MQTTHomeAutomationController
    language_service: LanguageService
    mcp_service: MCPService
    audio_feature_service: AudioFeatureService
    emotion_service: EmotionService
    automation_engine: AutomationEngine
    whisper_service: WhisperService
    tts_service: TTSService
    ai_router: AIRouterService


@asynccontextmanager
async def lifespan(app: FastAPI):
    default_mode: ModeLiteral = (
        settings.default_mode if settings.default_mode in {"online", "smart", "offline"} else "smart"
    )
    default_home_automation_mode = settings.home_automation_default

    openrouter_http = httpx.AsyncClient(
        base_url=settings.openrouter_base_url,
        timeout=settings.openrouter_timeout_s,
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
    )
    ollama_http = httpx.AsyncClient(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout_s,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )

    openrouter_client = OpenRouterClient(openrouter_http, settings)
    ollama_client = OllamaClient(ollama_http, settings)
    mcp_service = MCPService(settings)
    home_controller = MQTTHomeAutomationController(settings)
    mode_state = ModeState(default_mode=default_mode, default_home_automation_mode=default_home_automation_mode)

    home_controller.start()

    services = ServiceContainer(
        memory_store=MemoryStore(limit=settings.memory_limit),
        mode_state=mode_state,
        home_controller=home_controller,
        language_service=LanguageService(),
        mcp_service=mcp_service,
        audio_feature_service=AudioFeatureService(),
        emotion_service=EmotionService(),
        automation_engine=AutomationEngine(
            settings,
            mcp_service=mcp_service,
            mode_state=mode_state,
            home_controller=home_controller,
        ),
        whisper_service=WhisperService(settings),
        tts_service=TTSService(settings),
        ai_router=AIRouterService(
            settings=settings,
            openrouter_client=openrouter_client,
            ollama_client=ollama_client,
        ),
    )

    app.state.services = services

    try:
        yield
    finally:
        services.home_controller.stop()
        await openrouter_http.aclose()
        await ollama_http.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Compress JSON responses to reduce bandwidth and improve mobile latency.
app.add_middleware(GZipMiddleware, minimum_size=300)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_services(request: Request) -> ServiceContainer:
    return request.app.state.services


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/mode", response_model=ModeResponse)
async def set_mode(payload: ModeRequest, request: Request) -> ModeResponse:
    services = get_services(request)
    updated_mode = await services.mode_state.set_mode(payload.mode)
    return ModeResponse(mode=updated_mode)


@app.post("/home-mode", response_model=HomeModeResponse)
async def set_home_mode(payload: HomeModeRequest, request: Request) -> HomeModeResponse:
    services = get_services(request)
    enabled = await services.mode_state.set_home_automation_mode(payload.enabled)
    return HomeModeResponse(enabled=enabled)


@app.get("/home-mode", response_model=HomeModeResponse)
async def get_home_mode(request: Request) -> HomeModeResponse:
    services = get_services(request)
    enabled = await services.mode_state.is_home_automation_enabled()
    return HomeModeResponse(enabled=enabled)


@app.get("/home/status", response_model=HomeStatusResponse)
async def get_home_status(request: Request) -> HomeStatusResponse:
    services = get_services(request)
    return HomeStatusResponse.model_validate(services.home_controller.status_snapshot())


@app.post("/tts")
async def tts(payload: TTSRequest, request: Request) -> Response:
    services = get_services(request)
    synthesis = await services.tts_service.synthesize_bytes(payload.text, payload.language)
    if synthesis is None:
        raise HTTPException(status_code=503, detail="TTS is unavailable")

    audio_bytes, media_type = synthesis
    return Response(content=audio_bytes, media_type=media_type)


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, background_tasks: BackgroundTasks, request: Request) -> ChatResponse:
    services = get_services(request)
    detected_language = services.language_service.detect(payload.text)
    preferred_language_code = _normalize_preferred_language(payload.preferred_language)
    response_language = _resolve_response_language(detected_language, preferred_language_code)

    effective_mode: ModeLiteral = payload.mode or await services.mode_state.get_mode()
    history = await services.memory_store.get_messages()

    action = await services.automation_engine.detect_and_execute(payload.text, language_code=response_language.code)

    if _is_browser_action(action):
        response_text = _build_browser_action_response(action or {}, response_language.code)
    elif _is_home_action(action):
        response_text = _build_home_action_response(action or {}, response_language.code)
    else:
        response_text, _route = await services.ai_router.route_request(
            text=payload.text,
            mode=effective_mode,
            history=history,
            response_language=response_language.name,
        )

    volume = float(payload.volume or 0.0)
    pitch = round(110.0 + (volume * 220.0), 1)
    emotion = services.emotion_service.detect(payload.text, volume)

    await services.memory_store.add_turn(payload.text, response_text)

    if payload.synthesize:
        background_tasks.add_task(services.tts_service.synthesize_to_temp, response_text)

    return ChatResponse(
        text=response_text,
        language=response_language.code,
        emotion=emotion,
        audio_features=AudioFeatures(volume=round(volume, 3), pitch=pitch),
        action=action,
    )


@app.post("/voice", response_model=VoiceResponse)
async def voice(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: ModeLiteral | None = Form(default=None),
    preferred_language: str | None = Form(default=None),
    synthesize: bool = Form(default=False),
) -> VoiceResponse:
    services = get_services(request)

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    preferred_language_code = _normalize_preferred_language(preferred_language)
    whisper_language_hint = preferred_language_code if preferred_language_code and preferred_language_code != "en" else None

    feature_task = asyncio.create_task(services.audio_feature_service.extract_from_bytes(audio_bytes))

    try:
        transcription = await services.whisper_service.transcribe_with_metadata(
            audio_bytes,
            language_hint=whisper_language_hint,
        )
    except ValueError as exc:
        if not feature_task.done():
            feature_task.cancel()
        detail = str(exc)
        status_code = 413 if "too long" in detail.lower() else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        if not feature_task.done():
            feature_task.cancel()
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc

    transcript = transcription.text
    if not transcript:
        raise HTTPException(status_code=422, detail="Could not detect speech in the provided audio")

    audio_features = AudioFeatureResult(volume=0.0, pitch=160.0, speech_rate=0.0, duration_seconds=0.0)
    try:
        audio_features = await asyncio.wait_for(feature_task, timeout=0.12)
    except asyncio.TimeoutError:
        if not feature_task.done():
            feature_task.cancel()
    except Exception as exc:
        logger.debug("Audio feature extraction failed, using neutral defaults: %s", exc)

    detected_language = services.language_service.detect(transcript)
    detected_language = _merge_voice_language_detection(detected_language, transcription)
    response_language = _resolve_response_language(detected_language, preferred_language_code)

    effective_mode: ModeLiteral = mode or await services.mode_state.get_mode()
    history = await services.memory_store.get_messages()
    action = await services.automation_engine.detect_and_execute(transcript, language_code=response_language.code)

    if _is_browser_action(action):
        response_text = _build_browser_action_response(action or {}, response_language.code)
    elif _is_home_action(action):
        response_text = _build_home_action_response(action or {}, response_language.code)
    else:
        response_text, _route = await services.ai_router.route_request(
            text=transcript,
            mode=effective_mode,
            history=history,
            response_language=response_language.name,
        )

    emotion = services.emotion_service.detect(transcript, audio_features.volume)

    await services.memory_store.add_turn(transcript, response_text)

    if synthesize:
        background_tasks.add_task(services.tts_service.synthesize_to_temp, response_text)

    return VoiceResponse(
        transcript=transcript,
        text=response_text,
        language=response_language.code,
        emotion=emotion,
        audio_features=AudioFeatures(
            volume=audio_features.volume,
            pitch=audio_features.pitch,
        ),
        action=action,
    )


@app.websocket("/ws/orb")
async def ws_orb(websocket: WebSocket) -> None:
    await websocket.accept()
    services: ServiceContainer = websocket.app.state.services

    try:
        while True:
            raw_message = await websocket.receive_text()

            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "invalid_json"})
                continue

            audio_base64 = payload.get("audio_base64")
            if not isinstance(audio_base64, str) or not audio_base64:
                await websocket.send_json({"error": "audio_base64 is required"})
                continue

            try:
                features = await services.audio_feature_service.extract_from_base64(audio_base64)
            except Exception:
                await websocket.send_json({"error": "audio_processing_failed"})
                continue

            await websocket.send_json(features)
    except WebSocketDisconnect:
        return

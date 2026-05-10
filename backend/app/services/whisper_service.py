from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

import anyio
import numpy as np
import soundfile as sf

from app.config import Settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    duration_seconds: float
    language_code: str | None
    language_confidence: float


class WhisperService:
    """Lazy loaded Faster-Whisper transcription service."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._models: dict[str, object] = {}
        self._model_lock = asyncio.Lock()
        self._transcribe_semaphore = asyncio.Semaphore(1)

    async def transcribe_audio(self, audio_bytes: bytes, language_hint: str | None = None) -> str:
        result = await self.transcribe_with_metadata(audio_bytes, language_hint=language_hint)
        return result.text

    async def transcribe_with_metadata(
        self,
        audio_bytes: bytes,
        language_hint: str | None = None,
    ) -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", duration_seconds=0.0, language_code=None, language_confidence=0.0)

        normalized_language = _normalize_language_hint(language_hint)
        model = await self._get_model(normalized_language)

        try:
            if _requires_tempfile_decode(audio_bytes):
                audio_array, sr = await anyio.to_thread.run_sync(self._decode_with_ffmpeg_sync, audio_bytes)
            else:
                audio_array, sr = await anyio.to_thread.run_sync(self._decode_sync, audio_bytes)
        except Exception as decode_error:
            logger.debug("Audio decode unavailable; using tempfile transcription path: %s", decode_error)
            return await self._transcribe_via_tempfile(model, audio_bytes, normalized_language)

        if audio_array.size == 0:
            return TranscriptionResult(text="", duration_seconds=0.0, language_code=None, language_confidence=0.0)

        duration_seconds = float(audio_array.shape[0] / sr)
        if duration_seconds > self.settings.max_audio_seconds:
            raise ValueError(
                f"Audio chunk too long ({duration_seconds:.2f}s). "
                f"Send chunks up to {self.settings.max_audio_seconds}s."
            )

        processed_audio = await anyio.to_thread.run_sync(self._preprocess_audio_sync, audio_array, sr)
        audio_for_transcription = processed_audio if processed_audio.size else audio_array
        used_preprocessed_audio = audio_for_transcription is not audio_array

        async with self._transcribe_semaphore:
            text, language_code, language_confidence = await anyio.to_thread.run_sync(
                self._transcribe_sync,
                model,
                audio_for_transcription,
                normalized_language,
            )

        if not text and used_preprocessed_audio:
            # If denoising over-suppresses speech, retry once with raw decoded waveform.
            async with self._transcribe_semaphore:
                text, language_code, language_confidence = await anyio.to_thread.run_sync(
                    self._transcribe_sync,
                    model,
                    audio_array,
                    normalized_language,
                )

        return TranscriptionResult(
            text=text,
            duration_seconds=duration_seconds,
            language_code=language_code,
            language_confidence=language_confidence,
        )

    async def batch_transcribe(self, chunks: list[bytes]) -> list[str]:
        tasks = [self.transcribe_audio(chunk) for chunk in chunks]
        return await asyncio.gather(*tasks)

    async def _get_model(self, language_hint: str | None = None):
        model_size = self._resolve_model_size(language_hint)

        cached_model = self._models.get(model_size)
        if cached_model is not None:
            return cached_model

        async with self._model_lock:
            cached_model = self._models.get(model_size)
            if cached_model is not None:
                return cached_model

            def _load_model():
                from faster_whisper import WhisperModel

                return WhisperModel(
                    model_size,
                    device=self.settings.whisper_device,
                    compute_type=self.settings.whisper_compute_type,
                )

            model = await anyio.to_thread.run_sync(_load_model)
            self._models[model_size] = model
            return model

    def _resolve_model_size(self, language_hint: str | None) -> str:
        default_size = self.settings.whisper_model_size

        if language_hint and language_hint != "en":
            return self.settings.whisper_multilingual_model_size or default_size

        return default_size

    def _decode_sync(self, audio_bytes: bytes) -> tuple[np.ndarray, int]:
        with io.BytesIO(audio_bytes) as stream:
            audio, sr = sf.read(stream, dtype="float32", always_2d=False)

        signal = np.asarray(audio, dtype=np.float32)
        if signal.ndim == 2:
            signal = np.mean(signal, axis=1, dtype=np.float32)
        elif signal.ndim > 2:
            signal = signal.reshape(-1)

        return signal, int(sr)

    def _decode_with_ffmpeg_sync(self, audio_bytes: bytes) -> tuple[np.ndarray, int]:
        ffmpeg_binary = shutil.which("ffmpeg")
        if not ffmpeg_binary:
            raise RuntimeError("ffmpeg binary is unavailable")

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=_guess_audio_suffix(audio_bytes)) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            command = [
                ffmpeg_binary,
                "-nostdin",
                "-v",
                "error",
                "-i",
                temp_path,
                "-f",
                "f32le",
                "-ac",
                "1",
                "-ar",
                "16000",
                "pipe:1",
            ]
            result = subprocess.run(command, capture_output=True, check=False)
            if result.returncode != 0 or not result.stdout:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"ffmpeg decode failed: {stderr}")

            signal = np.frombuffer(result.stdout, dtype=np.float32).copy()
            return signal, 16000
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _preprocess_audio_sync(self, audio_array: np.ndarray, sr: int) -> np.ndarray:
        signal = np.asarray(audio_array, dtype=np.float32)
        if signal.size == 0:
            return signal

        # Remove DC component and clamp extremes.
        signal = signal - float(np.mean(signal))
        signal = np.clip(signal, -1.0, 1.0)

        # Light pre-emphasis helps speech stand out from low-frequency crowd rumble.
        emphasized = np.empty_like(signal)
        emphasized[0] = signal[0]
        emphasized[1:] = signal[1:] - (0.97 * signal[:-1])

        window = max(8, int(sr * 0.02))
        kernel = np.ones(window, dtype=np.float32) / float(window)
        envelope = np.convolve(np.abs(emphasized), kernel, mode="same")

        noise_floor = float(np.percentile(envelope, 25)) if envelope.size else 0.0
        threshold = max(0.006, noise_floor * 1.9)
        speech_mask = envelope > threshold

        # Keep short pauses as part of speech by dilating active regions.
        dilation = max(1, int(sr * 0.05))
        speech_mask = np.convolve(speech_mask.astype(np.float32), np.ones(dilation, dtype=np.float32), mode="same") > 0

        active_indices = np.flatnonzero(speech_mask)
        if active_indices.size:
            lead_pad = int(sr * 0.08)
            tail_pad = int(sr * 0.08)
            start = max(0, int(active_indices[0]) - lead_pad)
            end = min(emphasized.size, int(active_indices[-1]) + tail_pad)
            processed = emphasized[start:end]
            mask = speech_mask[start:end].astype(np.float32)
            processed = processed * mask
        else:
            processed = emphasized

        if processed.size < max(400, int(sr * 0.18)):
            processed = emphasized

        peak = float(np.max(np.abs(processed))) if processed.size else 0.0
        if peak > 0:
            processed = processed / max(peak, 1e-4)

        return processed.astype(np.float32)

    async def _transcribe_via_tempfile(
        self,
        model,
        audio_bytes: bytes,
        language_hint: str | None = None,
    ) -> TranscriptionResult:
        try:
            async with self._transcribe_semaphore:
                text, duration_seconds, language_code, language_confidence = await anyio.to_thread.run_sync(
                    self._transcribe_from_tempfile_sync,
                    model,
                    audio_bytes,
                    language_hint,
                )
        except Exception as fallback_error:
            logger.warning("Fallback transcription decode failed: %s", fallback_error)
            raise ValueError(
                "Unsupported or unreadable audio format. "
                "Send short chunks as audio/webm, audio/wav, audio/mp4, or audio/ogg."
            ) from fallback_error

        if duration_seconds > self.settings.max_audio_seconds:
            raise ValueError(
                f"Audio chunk too long ({duration_seconds:.2f}s). "
                f"Send chunks up to {self.settings.max_audio_seconds}s."
            )

        return TranscriptionResult(
            text=text,
            duration_seconds=duration_seconds,
            language_code=language_code,
            language_confidence=language_confidence,
        )

    def _transcribe_sync(
        self,
        model,
        audio_array: np.ndarray,
        language_hint: str | None = None,
    ) -> tuple[str, str | None, float]:
        attempts: list[tuple[bool, str | None]] = [
            (False, language_hint),
            (True, language_hint),
        ]
        if language_hint:
            attempts.append((True, None))

        best_text = ""
        best_language: str | None = None
        best_confidence = 0.0

        for robust, attempt_language in attempts:
            text, detected_language, language_probability, _duration = self._run_transcription_attempt(
                model,
                audio_array,
                language_hint=attempt_language,
                robust=robust,
            )

            if text:
                return text, detected_language, language_probability

            if language_probability > best_confidence:
                best_language = detected_language
                best_confidence = language_probability

        return best_text, best_language, best_confidence

    def _transcribe_from_tempfile_sync(
        self,
        model,
        audio_bytes: bytes,
        language_hint: str | None = None,
    ) -> tuple[str, float, str | None, float]:
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=_guess_audio_suffix(audio_bytes)) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            attempts: list[tuple[bool, str | None]] = [
                (False, language_hint),
                (True, language_hint),
            ]
            if language_hint:
                attempts.append((True, None))

            text = ""
            duration = 0.0
            detected_language: str | None = None
            language_probability = 0.0
            best_confidence = 0.0
            for robust, attempt_language in attempts:
                candidate_text, candidate_language, candidate_probability, candidate_duration = self._run_transcription_attempt(
                    model,
                    temp_path,
                    language_hint=attempt_language,
                    robust=robust,
                )
                if candidate_text:
                    text = candidate_text
                    detected_language = candidate_language
                    language_probability = candidate_probability
                    duration = candidate_duration
                    break

                if candidate_probability > best_confidence:
                    detected_language = candidate_language
                    language_probability = candidate_probability
                    best_confidence = candidate_probability
                    duration = candidate_duration

            return text, duration, detected_language, language_probability
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _run_transcription_attempt(
        self,
        model,
        source: np.ndarray | str,
        language_hint: str | None,
        robust: bool,
    ) -> tuple[str, str | None, float, float]:
        transcribe_kwargs = self._build_transcribe_kwargs(language_hint=language_hint, robust=robust)
        segments, info = model.transcribe(source, **transcribe_kwargs)
        text = " ".join(segment.text.strip() for segment in segments if segment.text).strip()
        detected_language = _normalize_language_hint(getattr(info, "language", None))
        language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        language_probability = max(0.0, min(1.0, language_probability))
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        return text, detected_language, language_probability, duration

    def _build_transcribe_kwargs(self, language_hint: str | None, robust: bool) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "beam_size": 2 if robust else 1,
            "best_of": 2 if robust else 1,
            "temperature": 0.0,
            "vad_filter": True,
            "vad_parameters": {
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 120,
            },
            "no_speech_threshold": 0.48,
            "log_prob_threshold": -1.0,
            "condition_on_previous_text": False,
            "task": "transcribe",
        }

        prompt = self._build_initial_prompt(language_hint)
        if prompt:
            kwargs["initial_prompt"] = prompt

        if language_hint:
            kwargs["language"] = language_hint
        return kwargs

    def _build_initial_prompt(self, language_hint: str | None) -> str | None:
        if language_hint and language_hint != "en":
            return None

        return (
            "Home automation commands: turn on lights, turn off lights, fan on, fan off, "
            "AC on, AC off, TV on, TV off, open curtains, close curtains, lock door, unlock door, "
            "all on, all off, good morning, good night, away mode, home mode, status check."
        )


def _guess_audio_suffix(audio_bytes: bytes) -> str:
    if audio_bytes.startswith(b"RIFF") and len(audio_bytes) >= 12 and audio_bytes[8:12] == b"WAVE":
        return ".wav"
    if audio_bytes.startswith(b"OggS"):
        return ".ogg"
    if audio_bytes.startswith(b"fLaC"):
        return ".flac"
    if audio_bytes.startswith(b"ID3"):
        return ".mp3"
    if audio_bytes[:2] == b"\xff\xfb":
        return ".mp3"
    if audio_bytes[:2] in {b"\xff\xf1", b"\xff\xf9"}:
        return ".aac"
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        return ".mp4"
    if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    return ".bin"


def _requires_tempfile_decode(audio_bytes: bytes) -> bool:
    if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return True

    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        return True

    return False


def _normalize_language_hint(language_hint: str | None) -> str | None:
    if not language_hint:
        return None

    lowered = language_hint.strip().lower()
    aliases = {
        "english": "en",
        "hindi": "hi",
        "tamil": "ta",
        "telugu": "te",
        "malayalam": "ml",
    }

    normalized = aliases.get(lowered, lowered)
    if normalized in {"en", "hi", "ta", "te", "ml"}:
        return normalized

    if "-" in normalized:
        base = normalized.split("-", 1)[0]
        if base in {"en", "hi", "ta", "te", "ml"}:
            return base

    return None

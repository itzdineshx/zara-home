import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ZaraCore from "@/components/ZaraCore";
import VoiceController from "@/components/VoiceController";
import ResponseDisplay from "@/components/ResponseDisplay";
import DashboardPanel from "@/components/DashboardPanel";
import SettingsPanel from "@/components/SettingsPanel";
import TopBar from "@/components/TopBar";
import { defaultSettings, orbPaletteHues, type VoicePersona, type ZaraSettings } from "@/lib/settings";
import { parseWakeWordTranscript } from "@/lib/voice-activation";
import {
  checkHealth,
  getHomeAutomationStatus,
  getHomeStatus,
  processVoice,
  setMode,
  setHomeAutomationEnabled,
  generateSpeech,
  sendChat,
  executeHomeAction,
  type BackendAction,
  type BackendEmotion,
  type HomeStatusResponse,
} from "@/lib/zara-api";

type OrbState = "idle" | "listening" | "thinking" | "speaking";

const AUTO_STOP_MS = 4500;
const LOOP_RESTART_DELAY_MS = 520;
const DEFAULT_ASSISTANT_GREETING = "Hello, I'm ZARA.";

function isGenericVoiceProgressHint(hint: string): boolean {
  return (
    hint === "Processing voice with ZARA backend..." ||
    hint === "Sending voice chunk..." ||
    hint === "Auto-sending voice chunk..." ||
    hint === "Loop: sending voice chunk..." ||
    hint === "Continuous loop active..." ||
    hint === "Scanning for wake word..." ||
    hint === "Wake word listening active..."
  );
}

function chooseRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return undefined;
  }

  const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return preferred.find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
}

function buildAudioConstraints(micSensitivity: number): MediaTrackConstraints {
  const normalized = Math.min(1, Math.max(0, micSensitivity / 100));
  const preferredSampleRate = normalized >= 0.65 ? 24000 : 16000;

  return {
    channelCount: { ideal: 1 },
    sampleRate: { ideal: preferredSampleRate },
    sampleSize: { ideal: 16 },
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
}

function truncate(text: string, maxLength: number) {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}...`;
}

function normalizeSpeechLanguageTag(language: string | undefined, fallback: string): string {
  const baseCodeMap: Record<string, string> = {
    en: "en-US",
    hi: "hi-IN",
    ta: "ta-IN",
    te: "te-IN",
    ml: "ml-IN",
  };

  const fallbackCode = fallback.trim().toLowerCase().split("-")[0];
  const resolvedFallback = baseCodeMap[fallbackCode] ?? "en-US";

  if (!language) {
    return resolvedFallback;
  }

  const lowered = language.trim().toLowerCase();
  if (!lowered) {
    return resolvedFallback;
  }

  const loweredCode = lowered.split("-")[0];
  return baseCodeMap[loweredCode] ?? resolvedFallback;
}

type SupportedLanguageCode = "en" | "hi" | "ta" | "te" | "ml";

function toSupportedLanguageCode(language: string | undefined): SupportedLanguageCode {
  const code = (language ?? "").trim().toLowerCase().split("-")[0];
  if (code === "hi" || code === "ta" || code === "te" || code === "ml") {
    return code;
  }
  return "en";
}

function localizeActionRuntimeHint(
  language: string | undefined,
  actionType: string,
  actionStatus: string,
  detail?: string,
): string {
  const code = toSupportedLanguageCode(language);

  if (code === "hi") {
    if (actionStatus === "executed" || actionStatus === "executed_fallback") {
      return `${actionType} कमांड पूरा हुआ`;
    }
    if (actionStatus === "failed") {
      return detail ? `${actionType} कमांड विफल: ${detail}` : `${actionType} कमांड विफल`;
    }
    if (actionStatus === "blocked_popup") {
      return `${actionType} कमांड ब्राउज़र पॉपअप सेटिंग से ब्लॉक हुआ`;
    }
    return `${actionType} कमांड स्थिति: ${actionStatus}`;
  }

  if (code === "ta") {
    if (actionStatus === "executed" || actionStatus === "executed_fallback") {
      return `${actionType} கட்டளை செயல்படுத்தப்பட்டது`;
    }
    if (actionStatus === "failed") {
      return detail ? `${actionType} கட்டளை தோல்வி: ${detail}` : `${actionType} கட்டளை தோல்வி`;
    }
    if (actionStatus === "blocked_popup") {
      return `${actionType} கட்டளை ப்ரௌசர் பாப்அப் அமைப்பால் தடுக்கப்பட்டது`;
    }
    return `${actionType} கட்டளை நிலை: ${actionStatus}`;
  }

  if (code === "te") {
    if (actionStatus === "executed" || actionStatus === "executed_fallback") {
      return `${actionType} కమాండ్ అమలైంది`;
    }
    if (actionStatus === "failed") {
      return detail ? `${actionType} కమాండ్ విఫలమైంది: ${detail}` : `${actionType} కమాండ్ విఫలమైంది`;
    }
    if (actionStatus === "blocked_popup") {
      return `${actionType} కమాండ్ బ్రౌజర్ పాప్-అప్ సెట్టింగ్స్ వల్ల నిలిపివేయబడింది`;
    }
    return `${actionType} కమాండ్ స్థితి: ${actionStatus}`;
  }

  if (code === "ml") {
    if (actionStatus === "executed" || actionStatus === "executed_fallback") {
      return `${actionType} കമാൻഡ് നടപ്പാക്കി`;
    }
    if (actionStatus === "failed") {
      return detail ? `${actionType} കമാൻഡ് പരാജയപ്പെട്ടു: ${detail}` : `${actionType} കമാൻഡ് പരാജയപ്പെട്ടു`;
    }
    if (actionStatus === "blocked_popup") {
      return `${actionType} കമാൻഡ് ബ്രൗസർ പോപ്പ്-അപ്പ് ക്രമീകരണങ്ങൾ കാരണം തടഞ്ഞു`;
    }
    return `${actionType} കമാൻഡ് നില: ${actionStatus}`;
  }

  if (actionStatus === "executed" || actionStatus === "executed_fallback") {
    return `Action ${actionType} executed`;
  }
  if (actionStatus === "failed") {
    return detail ? `Action ${actionType} failed: ${detail}` : `Action ${actionType} failed`;
  }
  if (actionStatus === "blocked_popup") {
    return `Action ${actionType} blocked by browser popup settings`;
  }
  return `Action ${actionType} ${actionStatus}`;
}

function localizeLoopStoppedHint(language: string | undefined): string {
  const code = toSupportedLanguageCode(language);
  if (code === "hi") {
    return "लूप मोड बंद कर दिया गया";
  }
  if (code === "ta") {
    return "லூப் மோடு நிறுத்தப்பட்டது";
  }
  if (code === "te") {
    return "లూప్ మోడ్ ఆపబడింది";
  }
  if (code === "ml") {
    return "ലൂപ്പ് മോഡ് നിർത്തി";
  }
  return "Loop mode stopped";
}

function localizeSpeechUnavailableHint(language: string | undefined): string {
  const code = toSupportedLanguageCode(language);
  if (code === "hi") {
    return "आवाज़ नहीं चल पाई। लूप मोड रोका गया।";
  }
  if (code === "ta") {
    return "குரல் வெளியீடு வரவில்லை. லூப் மோடு நிறுத்தப்பட்டது.";
  }
  if (code === "te") {
    return "వాయిస్ ప్లే కాలేదు. లూప్ మోడ్ ఆపబడింది.";
  }
  if (code === "ml") {
    return "ശബ്ദ ഔട്ട്‌പുട്ട് ലഭിച്ചില്ല. ലൂപ്പ് മോഡ് നിർത്തി.";
  }
  return "Voice output failed. Loop mode stopped.";
}

function shouldStopLoopFromTranscript(transcript: string): boolean {
  const normalized = transcript.trim().toLowerCase().replace(/\s+/g, " ");
  if (!normalized) {
    return false;
  }

  const explicitStopPhrases = [
    "stop loop",
    "loop off",
    "disable loop",
    "stop listening",
    "stop continuous",
    "लूप बंद",
    "लूप बंद करो",
    "सुनना बंद",
    "லூப் ஆஃப்",
    "லூப் நிறுத்து",
    "கேட்காதே",
    "లూప్ ఆఫ్",
    "లూప్ ఆపు",
    "వినడం ఆపు",
    "ലൂപ് ഓഫ്",
    "ലൂപ് നിർത്തു",
    "കേൾക്കൽ നിർത്തു",
  ];

  if (explicitStopPhrases.some((phrase) => normalized.includes(phrase))) {
    return true;
  }

  const hasLoopContext =
    /(loop|continuous|listen|listening|लूप|सुनना|லூப்|கேட்|లూప్|విన|ലൂപ്|കേൾക്ക)/.test(normalized);
  const hasStopIntent =
    /(stop|off|disable|pause|बंद|रोक|रुको|நிறுத்து|ஆஃப்|ஆப்|ఆపు|ఆఫ్|നിർത്തു|ഓഫ്|niruthu|aapu|nirthu|band)/.test(normalized);

  return hasLoopContext && hasStopIntent;
}

function actionString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

const femaleVoiceMarkers = [
  "female",
  "woman",
  "girl",
  "zira",
  "samantha",
  "victoria",
  "joanna",
  "ava",
  "aria",
  "jenny",
  "sara",
  "sonia",
];

const maleVoiceMarkers = [
  "male",
  "man",
  "david",
  "mark",
  "james",
  "daniel",
  "george",
  "alex",
  "ryan",
  "john",
];

function pickPreferredVoice(
  voices: SpeechSynthesisVoice[],
  language: string,
  persona: VoicePersona,
): SpeechSynthesisVoice | null {
  if (!voices.length) {
    return null;
  }

  const normalizedLanguage = language.toLowerCase();
  const langPrefix = normalizedLanguage.split("-")[0];

  const byLanguage = voices.filter((voice) => {
    const voiceLang = voice.lang.toLowerCase();
    return voiceLang === normalizedLanguage || voiceLang.startsWith(`${langPrefix}-`) || voiceLang.startsWith(langPrefix);
  });

  const pool = byLanguage.length ? byLanguage : voices;

  const matchByMarkers = (markers: string[]) =>
    pool.find((voice) => {
      const name = voice.name.toLowerCase();
      return markers.some((marker) => name.includes(marker));
    }) ?? null;

  if (persona === "female") {
    return matchByMarkers(femaleVoiceMarkers) ?? pool[0] ?? null;
  }

  if (persona === "male") {
    return matchByMarkers(maleVoiceMarkers) ?? pool[0] ?? null;
  }

  const defaultVoice = pool.find((voice) => voice.default);
  return defaultVoice ?? matchByMarkers(femaleVoiceMarkers) ?? pool[0] ?? null;
}

const Index = () => {
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<ZaraSettings>(defaultSettings);
  const [assistantText, setAssistantText] = useState("");
  const [showIntroGreeting, setShowIntroGreeting] = useState(true);
  const [lastTranscript, setLastTranscript] = useState("");
  const [lastLanguage, setLastLanguage] = useState("en");
  const [lastEmotion, setLastEmotion] = useState<BackendEmotion>("neutral");
  const [runtimeHint, setRuntimeHint] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [voiceSignal, setVoiceSignal] = useState({ volume: 0, pitch: 160 });
  const [backendHealth, setBackendHealth] = useState<string | null>(null);
  const [homeAutomationEnabled, setHomeAutomationEnabledState] = useState<boolean | null>(null);
  const [homeStatus, setHomeStatus] = useState<HomeStatusResponse | null>(null);
  const [dashboardUpdatedAt, setDashboardUpdatedAt] = useState<string | null>(null);
  const [dashboardStatusMessage, setDashboardStatusMessage] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const autoStopTimerRef = useRef<number | null>(null);
  const loopRestartTimerRef = useRef<number | null>(null);
  const processVoiceChunkRef = useRef<(audioChunk: Blob) => Promise<void>>(async () => undefined);
  const isProcessingRef = useRef(false);
  const mountedRef = useRef(true);
  const continuousLoopRef = useRef(settings.ai.continuousLoop);
  const previousLoopSettingRef = useRef(settings.ai.continuousLoop);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);

  const getPreferredVoice = useCallback(async (languageTag: string): Promise<SpeechSynthesisVoice | null> => {
    if (!("speechSynthesis" in window)) {
      return null;
    }

    const synth = window.speechSynthesis;
    let voices = synth.getVoices();

    if (!voices.length) {
      await new Promise<void>((resolve) => {
        const complete = () => {
          synth.removeEventListener("voiceschanged", complete);
          resolve();
        };

        synth.addEventListener("voiceschanged", complete, { once: true });
        window.setTimeout(complete, 450);
      });

      voices = synth.getVoices();
    }

    return pickPreferredVoice(voices, languageTag, settings.voice.persona);
  }, [settings.voice.persona]);

  const clearAutoStop = useCallback(() => {
    if (autoStopTimerRef.current !== null) {
      window.clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
  }, []);

  const clearLoopRestart = useCallback(() => {
    if (loopRestartTimerRef.current !== null) {
      window.clearTimeout(loopRestartTimerRef.current);
      loopRestartTimerRef.current = null;
    }
  }, []);

  const stopTtsAudio = useCallback(() => {
    const current = ttsAudioRef.current;
    if (!current) {
      return;
    }

    current.pause();
    current.currentTime = 0;
    ttsAudioRef.current = null;
  }, []);

  const releaseAudioStream = useCallback(() => {
    setOrbState("idle");
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setAudioStream(null);
  }, []);

  const handleAutomationAction = useCallback(
    (action: BackendAction | null, languageCode?: string): string | null => {
      if (!action) {
        return null;
      }

      const actionType = actionString(action.type) ?? "automation";
      const actionStatus = actionString(action.status) ?? "planned";
      const mcpTool = actionString(action.mcp_tool);
      const target = actionString(action.target) ?? actionString(action.mcp_url);
      const fallbackTarget = actionString(action.fallback_target);
      const spotifyUri = actionString(action.spotify_uri);
      const actionError = actionString(action.error);
      const actionLanguage = actionString(action.language) ?? languageCode;
      const isMediaAction =
        actionType === "spotify_play" ||
        actionType === "spotify_music" ||
        actionType === "open_spotify" ||
        actionType === "youtube_play" ||
        actionType === "open_youtube";
      const canClientExecuteOpenUrl = settings.automation.routines && mcpTool === "open_url" && !!target;

      if (actionStatus === "executed" || actionStatus === "executed_fallback") {
        return localizeActionRuntimeHint(actionLanguage, actionType, actionStatus);
      }

      if (actionStatus === "failed" && canClientExecuteOpenUrl) {
        const navigateUrl = fallbackTarget ?? target;
        if (isMediaAction) {
          if (spotifyUri) {
            const spotifyPopup = window.open(spotifyUri, "_blank", "noopener,noreferrer");
            if (spotifyPopup) {
              return localizeActionRuntimeHint(actionLanguage, actionType, "executed_fallback");
            }
          }

          const mediaPopup = window.open(target, "_blank", "noopener,noreferrer");
          if (mediaPopup) {
            return localizeActionRuntimeHint(actionLanguage, actionType, "executed_fallback");
          }

          window.location.assign(navigateUrl);
          return localizeActionRuntimeHint(actionLanguage, actionType, "executed_fallback");
        }

        const popup = window.open(target, "_blank", "noopener,noreferrer");
        if (popup) {
          return localizeActionRuntimeHint(actionLanguage, actionType, "executed_fallback");
        }

        window.location.assign(navigateUrl);
        return localizeActionRuntimeHint(actionLanguage, actionType, "executed_fallback");
      }

      if (actionStatus === "failed") {
        return localizeActionRuntimeHint(actionLanguage, actionType, actionStatus, actionError ?? undefined);
      }

      if (canClientExecuteOpenUrl && actionStatus === "planned") {
        if (isMediaAction) {
          if (spotifyUri) {
            const spotifyPopup = window.open(spotifyUri, "_blank", "noopener,noreferrer");
            if (spotifyPopup) {
              return localizeActionRuntimeHint(actionLanguage, actionType, "executed");
            }
          }

          const mediaPopup = window.open(target, "_blank", "noopener,noreferrer");
          if (mediaPopup) {
            return localizeActionRuntimeHint(actionLanguage, actionType, "executed");
          }

          const navigateUrl = fallbackTarget ?? target;
          window.location.assign(navigateUrl);
          return localizeActionRuntimeHint(actionLanguage, actionType, "executed");
        }

        const popup = window.open(target, "_blank", "noopener,noreferrer");
        if (popup) {
          return localizeActionRuntimeHint(actionLanguage, actionType, "executed");
        }

        return localizeActionRuntimeHint(actionLanguage, actionType, "blocked_popup");
      }

      return localizeActionRuntimeHint(actionLanguage, actionType, actionStatus);
    },
    [settings.automation.routines],
  );

  const startListening = useCallback(
    async (fromLoop = false, passiveWakeScan = false) => {
      if (isProcessingRef.current) {
        return;
      }

      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        return;
      }

      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        setRuntimeHint("This browser does not support microphone recording.");
        return;
      }

      stopTtsAudio();
      window.speechSynthesis?.cancel();
      clearLoopRestart();
      clearAutoStop();

      try {
        let stream: MediaStream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: buildAudioConstraints(settings.voice.micSensitivity),
          });
        } catch {
          // Retry with broad compatibility when strict constraints are unsupported.
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        }

        const mimeType = chooseRecorderMimeType();
        const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

        audioChunksRef.current = [];
        streamRef.current = stream;
        recorderRef.current = recorder;
        setAudioStream(stream);

        recorder.ondataavailable = (event: BlobEvent) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };

        recorder.onstop = () => {
          const chunkType = recorder.mimeType || "audio/webm";
          const chunk = new Blob(audioChunksRef.current, { type: chunkType });
          audioChunksRef.current = [];
          recorderRef.current = null;
          releaseAudioStream();

          if (chunk.size === 0) {
            setIsProcessing(false);
            setRuntimeHint("No voice captured. Please try again.");
            return;
          }

          void processVoiceChunkRef.current(chunk);
        };

        recorder.start();
        setOrbState("listening");
        if (passiveWakeScan) {
          setRuntimeHint("Wake word listening active...");
        } else {
          setRuntimeHint(fromLoop ? "Continuous loop listening..." : "Listening...");
        }

        autoStopTimerRef.current = window.setTimeout(() => {
          if (recorder.state !== "inactive") {
            setIsProcessing(true);
            if (passiveWakeScan) {
              setRuntimeHint("Scanning for wake word...");
            } else {
              setRuntimeHint(fromLoop ? "Loop: sending voice chunk..." : "Auto-sending voice chunk...");
            }
            recorder.stop();
          }
        }, AUTO_STOP_MS);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Microphone permission denied";
        setRuntimeHint(message);
        releaseAudioStream();
      }
    },
    [clearAutoStop, clearLoopRestart, releaseAudioStream, settings.voice.micSensitivity, stopTtsAudio],
  );

  const playBackendTts = useCallback(async (text: string, languageCode: SupportedLanguageCode): Promise<boolean> => {
    try {
      const audioBlob = await generateSpeech(text, languageCode);
      if (!audioBlob.size) {
        return false;
      }

      const objectUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(objectUrl);
      ttsAudioRef.current = audio;

      return await new Promise<boolean>((resolve) => {
        let finished = false;
        const complete = (success: boolean) => {
          if (finished) {
            return;
          }
          finished = true;
          audio.onended = null;
          audio.onerror = null;
          URL.revokeObjectURL(objectUrl);
          if (ttsAudioRef.current === audio) {
            ttsAudioRef.current = null;
          }
          resolve(success);
        };

        audio.onended = () => complete(true);
        audio.onerror = () => complete(false);

        const playPromise = audio.play();
        if (playPromise) {
          void playPromise.catch(() => complete(false));
        }
      });
    } catch {
      return false;
    }
  }, []);

  const speakResponse = useCallback(
    async (text: string, spokenLanguage?: string, preferLocalFirst = false): Promise<boolean> => {
      if (!text.trim()) {
        return false;
      }

      stopTtsAudio();
      window.speechSynthesis.cancel();

      if (preferLocalFirst && "speechSynthesis" in window) {
        const resolvedLanguage = normalizeSpeechLanguageTag(spokenLanguage, settings.voice.language);
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = resolvedLanguage;
        utterance.rate = Math.min(1.4, Math.max(0.75, settings.voice.voiceSpeed / 100));
        utterance.pitch = settings.voice.persona === "male" ? 0.94 : settings.voice.persona === "female" ? 1.08 : 1;

        const preferredVoice = await getPreferredVoice(resolvedLanguage);
        if (preferredVoice) {
          utterance.voice = preferredVoice;
          utterance.lang = preferredVoice.lang || resolvedLanguage;
        }

        const localSpeechStatus = await new Promise<"ended" | "error">((resolve) => {
          utterance.onend = () => resolve("ended");
          utterance.onerror = () => resolve("error");
          window.speechSynthesis.speak(utterance);
        });

        if (localSpeechStatus === "ended") {
          return true;
        }
      }

      const preferredCode = toSupportedLanguageCode(spokenLanguage ?? settings.voice.language);
      const playedByBackend = await playBackendTts(text, preferredCode);
      if (playedByBackend) {
        return true;
      }

      if (!("speechSynthesis" in window)) {
        return false;
      }

      const resolvedLanguage = normalizeSpeechLanguageTag(spokenLanguage, settings.voice.language);
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = resolvedLanguage;
      utterance.rate = Math.min(1.4, Math.max(0.75, settings.voice.voiceSpeed / 100));
      utterance.pitch = settings.voice.persona === "male" ? 0.94 : settings.voice.persona === "female" ? 1.08 : 1;

      const preferredVoice = await getPreferredVoice(resolvedLanguage);
      if (preferredVoice) {
        utterance.voice = preferredVoice;
        utterance.lang = preferredVoice.lang || resolvedLanguage;
      } else {
        utterance.lang = "en-US";
      }

      const startedAt = Date.now();
      const speechStatus = await new Promise<"ended" | "error">((resolve) => {
        utterance.onend = () => resolve("ended");
        utterance.onerror = () => resolve("error");
        window.speechSynthesis.speak(utterance);
      });

      if (speechStatus === "error") {
        return false;
      }

      const elapsedMs = Date.now() - startedAt;
      const likelySilentPlayback = text.trim().length >= 10 && elapsedMs < 220;
      return !likelySilentPlayback;
    },
    [getPreferredVoice, playBackendTts, settings.voice.language, settings.voice.persona, settings.voice.voiceSpeed, stopTtsAudio],
  );

  const processVoiceChunk = useCallback(
    async (audioChunk: Blob) => {
      let shouldContinueLoop = true;

      setOrbState("thinking");
      setRuntimeHint("Processing voice with ZARA backend...");
      setShowIntroGreeting(false);

      try {
        const response = await processVoice(audioChunk, settings.ai.responseMode, settings.voice.language);
        if (!mountedRef.current) return;

        setAssistantText(response.text);
        setLastTranscript(response.transcript);
        setLastEmotion(response.emotion);
        setLastLanguage(response.language);
        setVoiceSignal(response.audio_features);

        const wakeWord = parseWakeWordTranscript(response.transcript);
        const loopStopRequested = shouldStopLoopFromTranscript(response.transcript);
        const wasLoopEnabled = continuousLoopRef.current;

        if (!wasLoopEnabled && !wakeWord.wakeWordDetected) {
          setRuntimeHint("Scanning for 'Hi Zara' or 'Hello Zara'.");
          shouldContinueLoop = true;
          return;
        }

        if (loopStopRequested && wasLoopEnabled) {
          continuousLoopRef.current = false;
          setSettings((previous) => ({
            ...previous,
            ai: {
              ...previous.ai,
              continuousLoop: false,
            },
          }));
          setRuntimeHint(localizeLoopStoppedHint(response.language));
          return;
        }

        if (wakeWord.wakeWordDetected && !wasLoopEnabled) {
          continuousLoopRef.current = true;
          setSettings((previous) => ({
            ...previous,
            ai: {
              ...previous.ai,
              continuousLoop: true,
            },
          }));

          if (!wakeWord.command) {
            setRuntimeHint("Wake word detected. Listening...");
            return;
          }
        }

        const actionRuntimeHint = handleAutomationAction(response.action, response.language);
        const isExecutedHomeAction =
          actionString(response.action?.domain) === "home" && actionString(response.action?.status) === "executed";
        if (loopStopRequested && wasLoopEnabled) {
          setRuntimeHint(localizeLoopStoppedHint(response.language));
        } else if (actionRuntimeHint) {
          setRuntimeHint(actionRuntimeHint);
        } else {
          setRuntimeHint("");
        }

        setOrbState("speaking");
        const didSpeak = await speakResponse(response.text, response.language, isExecutedHomeAction);

        if (!didSpeak && continuousLoopRef.current) {
          continuousLoopRef.current = false;
          setSettings((previous) => ({
            ...previous,
            ai: {
              ...previous.ai,
              continuousLoop: false,
            },
          }));
          setRuntimeHint(localizeSpeechUnavailableHint(response.language));
          void speakResponse("Voice output failed. Loop mode stopped.", "en");
        }
      } catch (error) {
        if (!mountedRef.current) return;

        setShowIntroGreeting(false);
        const message = error instanceof Error ? error.message : "Voice request failed";
        setAssistantText("I couldn't process that voice request. Please try again.");
        setRuntimeHint(message);
      } finally {
        if (mountedRef.current) {
          setOrbState("idle");
          setIsProcessing(false);

          if (shouldContinueLoop) {
            setRuntimeHint(continuousLoopRef.current ? "Continuous loop active..." : "Scanning for wake word...");
            clearLoopRestart();
            loopRestartTimerRef.current = window.setTimeout(() => {
              if (!mountedRef.current) {
                return;
              }
              if (isProcessingRef.current) {
                return;
              }
              void startListening(continuousLoopRef.current, !continuousLoopRef.current);
            }, LOOP_RESTART_DELAY_MS);
          }
        }
      }
    },
    [clearLoopRestart, handleAutomationAction, settings.ai.responseMode, settings.voice.language, speakResponse, startListening],
  );

  useEffect(() => {
    processVoiceChunkRef.current = processVoiceChunk;
  }, [processVoiceChunk]);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      clearAutoStop();
      return;
    }

    recorder.stop();
    clearAutoStop();
  }, [clearAutoStop]);

  useEffect(() => {
    isProcessingRef.current = isProcessing;
  }, [isProcessing]);

  useEffect(() => {
    mountedRef.current = true;
    void startListening(true, true);
    return () => {
      mountedRef.current = false;
      stopRecording();
      releaseAudioStream();
      clearAutoStop();
      clearLoopRestart();
      stopTtsAudio();
      window.speechSynthesis?.cancel();
    };
  }, [clearAutoStop, clearLoopRestart, releaseAudioStream, startListening, stopRecording, stopTtsAudio]);

  useEffect(() => {
    const wasEnabled = previousLoopSettingRef.current;
    const isEnabled = settings.ai.continuousLoop;

    previousLoopSettingRef.current = isEnabled;
    continuousLoopRef.current = isEnabled;

    if (!isEnabled) {
      clearLoopRestart();
      return;
    }

    const recorder = recorderRef.current;
    const canAutoStart =
      !wasEnabled &&
      orbState === "idle" &&
      !isProcessingRef.current &&
      (!recorder || recorder.state === "inactive");

    if (canAutoStart) {
      setRuntimeHint("Continuous loop active...");
      void startListening(true, false);
    }
  }, [clearLoopRestart, orbState, settings.ai.continuousLoop, startListening]);

  useEffect(() => {
    let active = true;
    setMode(settings.ai.responseMode).catch((error) => {
      if (!active) return;
      const message = error instanceof Error ? error.message : "Unable to sync AI mode";
      setRuntimeHint(message);
    });

    return () => {
      active = false;
    };
  }, [settings.ai.responseMode]);

  useEffect(() => {
    let active = true;
    setHomeAutomationEnabled(settings.mode.homeAutomation).catch((error) => {
      if (!active) return;
      const message = error instanceof Error ? error.message : "Unable to sync Home Automation mode";
      setRuntimeHint(message);
    });

    return () => {
      active = false;
    };
  }, [settings.mode.homeAutomation]);

  const refreshDashboard = useCallback(async () => {
    const [healthResult, homeAutomationResult, homeStatusResult] = await Promise.allSettled([
      checkHealth(),
      getHomeAutomationStatus(),
      getHomeStatus(),
    ]);

    const messages: string[] = [];

    if (healthResult.status === "fulfilled") {
      setBackendHealth(healthResult.value.status);
    } else {
      messages.push(healthResult.reason instanceof Error ? healthResult.reason.message : "Backend health unavailable");
    }

    if (homeAutomationResult.status === "fulfilled") {
      setHomeAutomationEnabledState(homeAutomationResult.value.enabled);
    } else {
      messages.push(homeAutomationResult.reason instanceof Error ? homeAutomationResult.reason.message : "Home automation status unavailable");
    }

    if (homeStatusResult.status === "fulfilled") {
      setHomeStatus(homeStatusResult.value);
    } else {
      messages.push(homeStatusResult.reason instanceof Error ? homeStatusResult.reason.message : "MQTT status unavailable");
    }

    setDashboardUpdatedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    setDashboardStatusMessage(messages.length ? messages[0] : "Live dashboard refreshed");
  }, []);

  useEffect(() => {
    if (!dashboardOpen) {
      return;
    }

    void refreshDashboard();
    const intervalId = window.setInterval(() => {
      void refreshDashboard();
    }, 12000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [dashboardOpen, refreshDashboard]);

  // Check backend health on mount
  useEffect(() => {
    let active = true;
    checkHealth()
      .then(() => {
        if (active && mountedRef.current) {
          console.log("Backend health check passed");
        }
      })
      .catch((error) => {
        if (!active) return;
        const message = error instanceof Error ? error.message : "Backend health check failed";
        console.warn("Backend health check:", message);
      });

    return () => {
      active = false;
    };
  }, []);

  const messages = useMemo(() => {
    if (orbState === "listening") {
      return "I'm listening...";
    }
    if (orbState === "thinking") {
      return settings.ai.responseMode === "offline" ? "Processing locally..." : "Thinking...";
    }

    return assistantText;
  }, [assistantText, lastTranscript, orbState, runtimeHint, settings.ai.responseMode]);

  const heroSubtitle = useMemo(() => {
    if (!runtimeHint || isGenericVoiceProgressHint(runtimeHint)) {
      return undefined;
    }

    return runtimeHint;
  }, [runtimeHint]);

  const subtext = useMemo(() => {
    if (runtimeHint && !isGenericVoiceProgressHint(runtimeHint)) {
      return runtimeHint;
    }

    if (orbState === "listening") {
      return settings.ai.continuousLoop
        ? "Loop mode on. Tap once to send or pause between turns."
        : "Scanning for 'Hi Zara' or 'Hello Zara'.";
    }

    if (orbState === "speaking") {
      return `Emotion: ${lastEmotion} | Lang: ${lastLanguage}`;
    }

    if (lastTranscript) {
      return `Heard: ${truncate(lastTranscript, 90)}`;
    }

    return "";
  }, [lastEmotion, lastLanguage, lastTranscript, orbState, runtimeHint]);

  const heroTitle = showIntroGreeting ? DEFAULT_ASSISTANT_GREETING : "";

  const orbVisuals = useMemo(
    () => ({
      hue:
        (orbPaletteHues[settings.orb.palette] +
          (lastEmotion === "happy" ? 14 : lastEmotion === "angry" ? -24 : lastEmotion === "calm" ? 6 : 0) +
          360) %
        360,
      intensity: Math.min(100, Math.max(30, Math.round(settings.orb.intensity * 0.7 + voiceSignal.volume * 30))),
      reactivity: Math.min(100, Math.max(20, Math.round(settings.orb.reactivity * 0.65 + voiceSignal.volume * 35))),
      dimmed: settingsOpen,
    }),
    [lastEmotion, settings.orb.intensity, settings.orb.palette, settings.orb.reactivity, settingsOpen, voiceSignal.volume],
  );

  const handleMicToggle = useCallback(async () => {
    if (isProcessingRef.current) {
      return;
    }

    setShowIntroGreeting(false);

    if (orbState === "listening") {
      if (settings.ai.continuousLoop) {
        continuousLoopRef.current = false;
        setSettings((previous) => ({
          ...previous,
          ai: {
            ...previous.ai,
            continuousLoop: false,
          },
        }));
        setRuntimeHint(localizeLoopStoppedHint(lastLanguage));
      } else {
        setRuntimeHint("Sending voice chunk...");
      }
      setIsProcessing(true);
      stopRecording();
      return;
    }

    if (orbState !== "idle") {
      clearLoopRestart();
      clearAutoStop();
      stopTtsAudio();
      window.speechSynthesis?.cancel();
      releaseAudioStream();
      setOrbState("idle");
      setIsProcessing(false);
      setRuntimeHint("");
      return;
    }

    await startListening(false, false);
  }, [
    clearAutoStop,
    clearLoopRestart,
    lastLanguage,
    orbState,
    releaseAudioStream,
    settings.ai.continuousLoop,
    startListening,
    stopTtsAudio,
    stopRecording,
  ]);

  return (
    <div className="relative flex min-h-screen select-none flex-col items-center justify-center overflow-hidden bg-black">
      <TopBar
        mode={settings.ai.responseMode}
        presence={settings.mode.presence}
        homeAutomation={homeAutomationEnabled ?? settings.mode.homeAutomation}
        continuousLoop={settings.ai.continuousLoop}
        onOpenDashboard={() => {
          setSettingsOpen(false);
          setDashboardOpen(true);
        }}
        onOpenSettings={() => {
          setDashboardOpen(false);
          setSettingsOpen(true);
        }}
      />

      {/* Orb */}
      <motion.div
        className="relative z-10 flex flex-1 items-center justify-center"
        animate={
          dashboardOpen
            ? { opacity: 0.55, scale: 1.08, x: 30 }
            : settingsOpen
              ? { opacity: 0.55, scale: 1.12, x: -30 }
              : { opacity: 1, scale: 1.24, x: 0 }
        }
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <ZaraCore state={orbState} audioStream={audioStream} visuals={orbVisuals} title={heroTitle} subtitle={heroSubtitle} />
      </motion.div>

      {/* Text */}
      <ResponseDisplay text={messages} subtext={subtext} />

      {/* Mic */}
      <VoiceController orbState={orbState} onToggle={handleMicToggle} accentHue={orbVisuals.hue} />

      <DashboardPanel
        open={dashboardOpen}
        onOpenChange={(open) => {
          setDashboardOpen(open);
          if (open) {
            setSettingsOpen(false);
          }
        }}
        settings={settings}
        orbState={orbState}
        assistantText={assistantText}
        runtimeHint={runtimeHint}
        lastTranscript={lastTranscript}
        lastLanguage={lastLanguage}
        lastEmotion={lastEmotion}
        voiceSignal={voiceSignal}
        backendHealth={backendHealth}
        homeAutomationEnabled={homeAutomationEnabled}
        homeStatus={homeStatus}
        dashboardUpdatedAt={dashboardUpdatedAt}
        dashboardStatusMessage={dashboardStatusMessage}
        onRefresh={refreshDashboard}
      />

      <SettingsPanel
        open={settingsOpen}
        onOpenChange={(open) => {
          setSettingsOpen(open);
          if (open) {
            setDashboardOpen(false);
          }
        }}
        settings={settings}
        onSettingsChange={setSettings}
      />
    </div>
  );
};

export default Index;

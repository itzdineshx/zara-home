export type ResponseMode = "online" | "smart" | "offline";
export type PresenceMode = "virtual" | "physical";
export type PersonalityTone = "balanced" | "concise" | "expressive";
export type VoiceEngine = "neural" | "classic" | "local";
export type VoicePersona = "auto" | "female" | "male";
export type VoiceLanguage =
  | "en-US"
  | "hi-IN"
  | "ta-IN"
  | "te-IN"
  | "ml-IN";
export type OrbPalette = "cyan" | "ice" | "white";

export interface ZaraSettings {
  ai: {
    responseMode: ResponseMode;
    adaptiveReasoning: boolean;
    proactiveHints: boolean;
    continuousLoop: boolean;
  };
  personality: {
    tone: PersonalityTone;
    empathyBoost: boolean;
  };
  voice: {
    micSensitivity: number;
    voiceSpeed: number;
    language: VoiceLanguage;
    engine: VoiceEngine;
    persona: VoicePersona;
  };
  orb: {
    palette: OrbPalette;
    intensity: number;
    reactivity: number;
  };
  mode: {
    presence: PresenceMode;
    homeAutomation: boolean;
  };
  automation: {
    routines: boolean;
    ambientTriggers: boolean;
  };
  memory: {
    memoryEnabled: boolean;
    longTermMemory: boolean;
  };
  privacy: {
    onDeviceOnly: boolean;
    retainVoiceLogs: boolean;
  };
  advanced: {
    telemetry: boolean;
    debugSignals: boolean;
  };
}

export const orbPaletteHues: Record<OrbPalette, number> = {
  cyan: 190,
  ice: 205,
  white: 0,
};

export const defaultSettings: ZaraSettings = {
  ai: {
    responseMode: "smart",
    adaptiveReasoning: true,
    proactiveHints: false,
    continuousLoop: false,
  },
  personality: {
    tone: "balanced",
    empathyBoost: true,
  },
  voice: {
    micSensitivity: 62,
    voiceSpeed: 100,
    language: "en-US",
    engine: "neural",
    persona: "female",
  },
  orb: {
    palette: "cyan",
    intensity: 68,
    reactivity: 72,
  },
  mode: {
    presence: "virtual",
    homeAutomation: true,
  },
  automation: {
    routines: true,
    ambientTriggers: false,
  },
  memory: {
    memoryEnabled: true,
    longTermMemory: true,
  },
  privacy: {
    onDeviceOnly: false,
    retainVoiceLogs: false,
  },
  advanced: {
    telemetry: false,
    debugSignals: false,
  },
};

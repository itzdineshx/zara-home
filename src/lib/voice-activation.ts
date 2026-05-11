export type WakeWordParseResult = {
  wakeWordDetected: boolean;
  command: string | null;
};

function normalizeWakeWordText(text: string): string {
  // Use unicode property escapes to keep letters from any language, numbers, and whitespace.
  return text.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
}

export function parseWakeWordTranscript(transcript: string): WakeWordParseResult {
  const normalized = normalizeWakeWordText(transcript);
  
  const wakeWords = "zara|ஜாரா|சாரா|ज़ारा|जारा|జారా|సారా|സാറ|ജാറ";
  const greetings = "hi|hello|hey|ok|okay|வணக்கம்|नमस्ते|నమస్తే|നമസ്കാരം";
  
  const regex = new RegExp(`^(?:(?:${greetings})\\s+)?(?:${wakeWords})(?:\\s+(?<command>.+))?$`);
  const match = normalized.match(regex);

  if (!match) {
    return { wakeWordDetected: false, command: null };
  }

  const command = match.groups?.command?.trim() ?? "";

  return {
    wakeWordDetected: true,
    command: command.length ? command : null,
  };
}

export function isWakeWordTranscript(transcript: string): boolean {
  return parseWakeWordTranscript(transcript).wakeWordDetected;
}
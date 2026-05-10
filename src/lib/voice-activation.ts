export type WakeWordParseResult = {
  wakeWordDetected: boolean;
  command: string | null;
};

function normalizeWakeWordText(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}

export function parseWakeWordTranscript(transcript: string): WakeWordParseResult {
  const normalized = normalizeWakeWordText(transcript);
  const match = normalized.match(/^(hi|hello)\s+zara(?:\s+(?<command>.+))?$/);

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
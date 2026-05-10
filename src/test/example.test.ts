import { describe, it, expect } from "vitest";

import { parseWakeWordTranscript } from "@/lib/voice-activation";

describe("example", () => {
  it("detects the Zara wake phrases", () => {
    expect(parseWakeWordTranscript("Hi Zara")).toEqual({ wakeWordDetected: true, command: null });
    expect(parseWakeWordTranscript("hello zara")).toEqual({ wakeWordDetected: true, command: null });
  });

  it("ignores non-wake transcripts", () => {
    expect(parseWakeWordTranscript("turn on lights")).toEqual({ wakeWordDetected: false, command: null });
  });
});

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  BrainCircuit,
  ChevronDown,
  Languages,
  Mic2,
  Radar,
  Scan,
  Shield,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  Workflow,
} from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type {
  OrbPalette,
  PersonalityTone,
  PresenceMode,
  ResponseMode,
  VoiceEngine,
  VoiceLanguage,
  VoicePersona,
  ZaraSettings,
} from "@/lib/settings";

interface SettingsPanelProps {
  open: boolean;
  settings: ZaraSettings;
  onOpenChange: (open: boolean) => void;
  onSettingsChange: (settings: ZaraSettings) => void;
}

type SegmentedOption<T extends string> = {
  value: T;
  label: string;
};

type SettingRowProps = {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  hint?: string;
  children: React.ReactNode;
  alignTop?: boolean;
};

const sectionTitleClass = "text-[10px] uppercase tracking-[0.26em] text-white/35";

const modeOptions: SegmentedOption<ResponseMode>[] = [
  { value: "online", label: "Online" },
  { value: "smart", label: "Smart" },
  { value: "offline", label: "Offline" },
];

const presenceOptions: SegmentedOption<PresenceMode>[] = [
  { value: "virtual", label: "Virtual" },
  { value: "physical", label: "Physical" },
];

const toneOptions: SegmentedOption<PersonalityTone>[] = [
  { value: "balanced", label: "Balanced" },
  { value: "concise", label: "Concise" },
  { value: "expressive", label: "Expressive" },
];

const voicePersonaOptions: SegmentedOption<VoicePersona>[] = [
  { value: "auto", label: "Auto" },
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
];

function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (next: T) => void;
  options: SegmentedOption<T>[];
}) {
  return (
    <div className="inline-flex rounded-full border border-white/12 bg-white/[0.03] p-1">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-full px-3 py-1 text-[11px] font-light tracking-wide text-white/55 transition-all duration-300",
              active && "bg-cyan-300/10 text-[#EAEAEA] shadow-[0_0_20px_rgba(34,211,238,0.14)]",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function SettingRow({ icon: Icon, label, hint, children, alignTop = false }: SettingRowProps) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-center", alignTop && "sm:items-start")}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-white/38" />
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-light tracking-wide text-[#EAEAEA]">{label}</p>
        {hint ? <p className="text-[11px] text-white/40">{hint}</p> : null}
      </div>
      <div className="shrink-0 self-start sm:self-auto">{children}</div>
    </div>
  );
}

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <p className={sectionTitleClass}>{title}</p>
      {children}
    </section>
  );
}

const panelVariants = {
  hidden: { opacity: 0, x: 16 },
  show: {
    opacity: 1,
    x: 0,
    transition: {
      duration: 0.4,
      ease: [0.22, 1, 0.36, 1],
      staggerChildren: 0.05,
      delayChildren: 0.05,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, x: 10, filter: "blur(4px)" },
  show: { opacity: 1, x: 0, filter: "blur(0px)", transition: { duration: 0.4, ease: "easeOut" } },
};

const SettingsPanel = ({ open, settings, onOpenChange, onSettingsChange }: SettingsPanelProps) => {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const update = (next: ZaraSettings) => onSettingsChange(next);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full max-w-none border-l border-white/10 bg-black/70 p-0 text-[#EAEAEA] backdrop-blur-2xl sm:w-[92vw] sm:max-w-[380px] lg:max-w-[420px]"
      >
        <motion.div className="flex h-full flex-col" variants={panelVariants} initial="hidden" animate="show">
          <motion.div variants={itemVariants}>
            <SheetHeader className="space-y-1 px-4 pb-3 pt-5 text-left sm:px-5 sm:pt-6">
              <SheetTitle className="text-sm font-light tracking-[0.2em] uppercase text-white/90">ZARA AI</SheetTitle>
              <SheetDescription className="text-[11px] leading-relaxed text-white/45">Control layer for voice-first intelligence</SheetDescription>
            </SheetHeader>
          </motion.div>

          <div className="no-scrollbar flex-1 space-y-7 overflow-y-auto px-4 pb-8 sm:space-y-8 sm:px-5">
            <motion.div variants={itemVariants}>
              <SettingsSection title="AI Control">
              <SettingRow icon={BrainCircuit} label="Reasoning Mode" alignTop>
                <SegmentedControl
                  value={settings.ai.responseMode}
                  onChange={(next) =>
                    update({
                      ...settings,
                      ai: {
                        ...settings.ai,
                        responseMode: next,
                      },
                    })
                  }
                  options={modeOptions}
                />
              </SettingRow>
              <SettingRow icon={Sparkles} label="Adaptive Reasoning">
                <Switch
                  checked={settings.ai.adaptiveReasoning}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      ai: {
                        ...settings.ai,
                        adaptiveReasoning: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
              <SettingRow icon={Scan} label="Proactive Hints">
                <Switch
                  checked={settings.ai.proactiveHints}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      ai: {
                        ...settings.ai,
                        proactiveHints: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
              <SettingRow icon={Workflow} label="Continuous Loop" hint="Always-on listening is enabled">
                <Switch
                  checked={settings.ai.continuousLoop}
                  disabled
                  onCheckedChange={() => undefined}
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Personality">
              <SettingRow icon={UserRound} label="Tone" alignTop>
                <SegmentedControl
                  value={settings.personality.tone}
                  onChange={(next) =>
                    update({
                      ...settings,
                      personality: {
                        ...settings.personality,
                        tone: next,
                      },
                    })
                  }
                  options={toneOptions}
                />
              </SettingRow>
              <SettingRow icon={Bot} label="Empathy Boost">
                <Switch
                  checked={settings.personality.empathyBoost}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      personality: {
                        ...settings.personality,
                        empathyBoost: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Voice">
              <div className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-start gap-3 sm:items-center">
                    <Mic2 className="h-4 w-4 shrink-0 text-white/38" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[12px] font-light tracking-wide text-[#EAEAEA]">Mic Sensitivity</p>
                    </div>
                    <span className="text-[11px] text-white/45">{settings.voice.micSensitivity}%</span>
                  </div>
                  <Slider
                    min={0}
                    max={100}
                    step={1}
                    value={[settings.voice.micSensitivity]}
                    onValueChange={([value]) =>
                      update({
                        ...settings,
                        voice: {
                          ...settings.voice,
                          micSensitivity: value,
                        },
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-start gap-3 sm:items-center">
                    <Radar className="h-4 w-4 shrink-0 text-white/38" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[12px] font-light tracking-wide text-[#EAEAEA]">Voice Speed</p>
                    </div>
                    <span className="text-[11px] text-white/45">{settings.voice.voiceSpeed}%</span>
                  </div>
                  <Slider
                    min={70}
                    max={130}
                    step={1}
                    value={[settings.voice.voiceSpeed]}
                    onValueChange={([value]) =>
                      update({
                        ...settings,
                        voice: {
                          ...settings.voice,
                          voiceSpeed: value,
                        },
                      })
                    }
                  />
                </div>

                <SettingRow icon={Languages} label="Language">
                  <Select
                    value={settings.voice.language}
                    onValueChange={(value: VoiceLanguage) =>
                      update({
                        ...settings,
                        voice: {
                          ...settings.voice,
                          language: value,
                        },
                      })
                    }
                  >
                    <SelectTrigger className="h-8 w-full min-w-0 rounded-full border-white/10 bg-white/[0.02] px-3 text-xs text-white/80 focus:ring-1 focus:ring-cyan-300/30 sm:w-[148px]">
                      <SelectValue placeholder="Language" />
                    </SelectTrigger>
                    <SelectContent className="border-white/10 bg-black text-white">
                      <SelectItem value="en-US">English (US)</SelectItem>
                      <SelectItem value="hi-IN">Hindi</SelectItem>
                      <SelectItem value="ta-IN">Tamil</SelectItem>
                      <SelectItem value="te-IN">Telugu</SelectItem>
                      <SelectItem value="ml-IN">Malayalam</SelectItem>
                    </SelectContent>
                  </Select>
                </SettingRow>

                <SettingRow icon={SlidersHorizontal} label="Voice Engine">
                  <Select
                    value={settings.voice.engine}
                    onValueChange={(value: VoiceEngine) =>
                      update({
                        ...settings,
                        voice: {
                          ...settings.voice,
                          engine: value,
                        },
                      })
                    }
                  >
                    <SelectTrigger className="h-8 w-full min-w-0 rounded-full border-white/10 bg-white/[0.02] px-3 text-xs text-white/80 focus:ring-1 focus:ring-cyan-300/30 sm:w-[148px]">
                      <SelectValue placeholder="Engine" />
                    </SelectTrigger>
                    <SelectContent className="border-white/10 bg-black text-white">
                      <SelectItem value="neural">Neural</SelectItem>
                      <SelectItem value="classic">Classic</SelectItem>
                      <SelectItem value="local">Local</SelectItem>
                    </SelectContent>
                  </Select>
                </SettingRow>

                <SettingRow icon={Bot} label="Voice Persona" alignTop>
                  <SegmentedControl
                    value={settings.voice.persona}
                    onChange={(next) =>
                      update({
                        ...settings,
                        voice: {
                          ...settings.voice,
                          persona: next,
                        },
                      })
                    }
                    options={voicePersonaOptions}
                  />
                </SettingRow>
              </div>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Orb Visuals">
              <SettingRow icon={Sparkles} label="Palette">
                <Select
                  value={settings.orb.palette}
                  onValueChange={(value: OrbPalette) =>
                    update({
                      ...settings,
                      orb: {
                        ...settings.orb,
                        palette: value,
                      },
                    })
                  }
                >
                  <SelectTrigger className="h-8 w-[148px] rounded-full border-white/10 bg-white/[0.02] px-3 text-xs text-white/80 focus:ring-1 focus:ring-cyan-300/30">
                    <SelectValue placeholder="Palette" />
                  </SelectTrigger>
                  <SelectContent className="border-white/10 bg-black text-white">
                    <SelectItem value="cyan">Neural Cyan</SelectItem>
                    <SelectItem value="ice">Ice Blue</SelectItem>
                    <SelectItem value="white">Pure White</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>

              <div className="space-y-2">
                  <div className="flex items-start gap-3 sm:items-center">
                  <Sparkles className="h-4 w-4 shrink-0 text-white/38" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-light tracking-wide text-[#EAEAEA]">Intensity</p>
                  </div>
                  <span className="text-[11px] text-white/45">{settings.orb.intensity}%</span>
                </div>
                <Slider
                  min={30}
                  max={100}
                  step={1}
                  value={[settings.orb.intensity]}
                  onValueChange={([value]) =>
                    update({
                      ...settings,
                      orb: {
                        ...settings.orb,
                        intensity: value,
                      },
                    })
                  }
                />
              </div>

              <div className="space-y-2">
                  <div className="flex items-start gap-3 sm:items-center">
                  <Radar className="h-4 w-4 shrink-0 text-white/38" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-light tracking-wide text-[#EAEAEA]">Reactivity</p>
                  </div>
                  <span className="text-[11px] text-white/45">{settings.orb.reactivity}%</span>
                </div>
                <Slider
                  min={20}
                  max={100}
                  step={1}
                  value={[settings.orb.reactivity]}
                  onValueChange={([value]) =>
                    update({
                      ...settings,
                      orb: {
                        ...settings.orb,
                        reactivity: value,
                      },
                    })
                  }
                />
              </div>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Mode">
              <SettingRow icon={Workflow} label="Presence" alignTop>
                <SegmentedControl
                  value={settings.mode.presence}
                  onChange={(next) =>
                    update({
                      ...settings,
                      mode: {
                        ...settings.mode,
                        presence: next,
                      },
                    })
                  }
                  options={presenceOptions}
                />
              </SettingRow>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Automation">
              <SettingRow icon={Workflow} label="Routines">
                <Switch
                  checked={settings.automation.routines}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      automation: {
                        ...settings.automation,
                        routines: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
              <SettingRow icon={Scan} label="Ambient Triggers">
                <Switch
                  checked={settings.automation.ambientTriggers}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      automation: {
                        ...settings.automation,
                        ambientTriggers: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Memory">
              <SettingRow icon={BrainCircuit} label="Memory Layer">
                <Switch
                  checked={settings.memory.memoryEnabled}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      memory: {
                        ...settings.memory,
                        memoryEnabled: checked,
                        longTermMemory: checked ? settings.memory.longTermMemory : false,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
              <SettingRow icon={Bot} label="Long-Term Recall" hint={!settings.memory.memoryEnabled ? "Enable Memory Layer first" : undefined}>
                <Switch
                  checked={settings.memory.longTermMemory}
                  disabled={!settings.memory.memoryEnabled}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      memory: {
                        ...settings.memory,
                        longTermMemory: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
            </SettingsSection>
            </motion.div>

            <motion.div variants={itemVariants}>
              <SettingsSection title="Privacy">
              <SettingRow icon={Shield} label="On-device Processing">
                <Switch
                  checked={settings.privacy.onDeviceOnly}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      privacy: {
                        ...settings.privacy,
                        onDeviceOnly: checked,
                        retainVoiceLogs: checked ? false : settings.privacy.retainVoiceLogs,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
              <SettingRow icon={Mic2} label="Retain Voice Logs" hint={settings.privacy.onDeviceOnly ? "Disabled while on-device processing is active" : undefined}>
                <Switch
                  checked={settings.privacy.retainVoiceLogs}
                  disabled={settings.privacy.onDeviceOnly}
                  onCheckedChange={(checked) =>
                    update({
                      ...settings,
                      privacy: {
                        ...settings.privacy,
                        retainVoiceLogs: checked,
                      },
                    })
                  }
                  className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                />
              </SettingRow>
            </SettingsSection>
            </motion.div>

            <motion.section variants={itemVariants} className="space-y-3 pb-2">
              <button
                type="button"
                onClick={() => setAdvancedOpen((prev) => !prev)}
                className="flex w-full items-center justify-between rounded-full border border-white/10 bg-white/[0.02] px-3 py-2 text-[11px] uppercase tracking-[0.22em] text-white/55 transition-colors duration-300 hover:border-cyan-300/30 hover:text-white/80"
              >
                Advanced Settings
                <ChevronDown className={cn("h-4 w-4 transition-transform duration-300", advancedOpen && "rotate-180")} />
              </button>

              <AnimatePresence initial={false}>
                {advancedOpen ? (
                  <motion.div
                    key="advanced"
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    className="space-y-3"
                  >
                    <SettingRow icon={Radar} label="Telemetry">
                      <Switch
                        checked={settings.advanced.telemetry}
                        onCheckedChange={(checked) =>
                          update({
                            ...settings,
                            advanced: {
                              ...settings.advanced,
                              telemetry: checked,
                            },
                          })
                        }
                        className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                      />
                    </SettingRow>
                    <SettingRow icon={Scan} label="Debug Signals">
                      <Switch
                        checked={settings.advanced.debugSignals}
                        onCheckedChange={(checked) =>
                          update({
                            ...settings,
                            advanced: {
                              ...settings.advanced,
                              debugSignals: checked,
                            },
                          })
                        }
                        className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                      />
                    </SettingRow>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </motion.section>
          </div>
        </motion.div>
      </SheetContent>
    </Sheet>
  );
};

export default SettingsPanel;

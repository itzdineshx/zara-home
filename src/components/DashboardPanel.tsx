import { useMemo, useState, type ComponentType } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  Clock3,
  Cpu,
  Gauge,
  Home,
  Lightbulb,
  PlugZap,
  Radar,
  RefreshCw,
  ShieldAlert,
  Signal,
  Sparkles,
  Thermometer,
  Tv,
  Waves,
} from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { executeHomeAction, type HomeAction, type HomeStatusResponse } from "@/lib/zara-api";
import type { ZaraSettings } from "@/lib/settings";

type OrbState = "idle" | "listening" | "thinking" | "speaking";

interface DashboardPanelProps {
  open: boolean;
  settings: ZaraSettings;
  orbState: OrbState;
  assistantText: string;
  runtimeHint: string;
  lastTranscript: string;
  lastLanguage: string;
  lastEmotion: string;
  voiceSignal: {
    volume: number;
    pitch: number;
  };
  backendHealth: string | null;
  homeAutomationEnabled: boolean | null;
  homeStatus: HomeStatusResponse | null;
  dashboardUpdatedAt: string | null;
  dashboardStatusMessage: string | null;
  onOpenChange: (open: boolean) => void;
  onRefresh: () => Promise<void>;
}

type EntryView = {
  key: string;
  value: unknown;
  group: string;
  icon: ComponentType<{ className?: string }>;
  stateLabel: string;
  toneClass: string;
};

type RoomDevice = {
  id: string;
  label: string;
  on: boolean;
  actionOn: HomeAction;
  actionOff: HomeAction;
  description: string;
};

function MetricCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 shadow-[0_0_30px_rgba(0,0,0,0.2)]">
      <div className="flex items-center gap-3">
        <div className="rounded-full border border-cyan-300/12 bg-cyan-300/8 p-2 text-cyan-100/90">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.24em] text-white/38">{label}</p>
          <p className="mt-1 truncate text-sm font-light text-[#EAEAEA]">{value}</p>
          {hint ? <p className="mt-1 text-[11px] text-white/40">{hint}</p> : null}
        </div>
      </div>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null) return "null";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return "unknown";
}

function formatSnapshotAge(value: string | null): string {
  if (!value) return "No status packet yet";

  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;

  const ageMs = Date.now() - timestamp.getTime();
  if (ageMs < 0) return "Just now";

  const seconds = Math.floor(ageMs / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

function inferEntityGroup(key: string): { label: string; icon: ComponentType<{ className?: string }> } {
  const normalized = key.toLowerCase();

  if (/(light|lamp|led)/.test(normalized)) return { label: "Lighting", icon: Lightbulb };
  if (/(fan|ac|climate|temperature|therm|humidity|air)/.test(normalized)) return { label: "Climate", icon: Thermometer };
  if (/(tv|media|speaker|music|audio)/.test(normalized)) return { label: "Media", icon: Tv };
  if (/(door|lock|window|curtain|gate|security|camera)/.test(normalized)) return { label: "Access", icon: ShieldAlert };
  if (/(motion|presence|occupancy|sensor|pir)/.test(normalized)) return { label: "Sensors", icon: Radar };
  return { label: "Ecosystem", icon: Home };
}

function describeState(value: unknown): { label: string; toneClass: string } {
  if (typeof value === "boolean") {
    return value ? { label: "Active", toneClass: "text-emerald-200/90" } : { label: "Idle", toneClass: "text-white/55" };
  }

  if (typeof value === "number") {
    return { label: `${Math.round(value)}`, toneClass: "text-cyan-100/90" };
  }

  if (typeof value === "string") {
    const lower = value.toLowerCase();
    if (["on", "open", "unlocked", "active", "connected", "true", "running", "occupied"].includes(lower)) {
      return { label: value, toneClass: "text-emerald-200/90" };
    }
    if (["off", "closed", "locked", "inactive", "disconnected", "false"].includes(lower)) {
      return { label: value, toneClass: "text-white/55" };
    }
    return { label: value, toneClass: "text-cyan-100/85" };
  }

  if (Array.isArray(value)) {
    return { label: `${value.length} items`, toneClass: "text-cyan-100/85" };
  }

  if (value && typeof value === "object") {
    return { label: "Object snapshot", toneClass: "text-cyan-100/85" };
  }

  return { label: "Unknown", toneClass: "text-white/45" };
}

function calculateEcosystemScore({
  connected,
  snapshotAgeMs,
  entryCount,
  activeCount,
}: {
  connected: boolean;
  snapshotAgeMs: number | null;
  entryCount: number;
  activeCount: number;
}): number {
  let score = 30;

  if (connected) score += 30;
  if (entryCount > 0) score += Math.min(15, entryCount * 2);
  if (activeCount > 0) score += Math.min(15, activeCount * 2);

  if (snapshotAgeMs !== null) {
    if (snapshotAgeMs < 30_000) score += 10;
    else if (snapshotAgeMs < 120_000) score += 6;
    else if (snapshotAgeMs < 300_000) score += 2;
    else score -= 8;
  }

  return Math.max(0, Math.min(100, score));
}

const ADVANCED_ACTIONS: Array<{ label: string; action: HomeAction; description: string }> = [
  { label: "Run Status Check", action: "status_check", description: "Poll every connected node and refresh telemetry" },
  { label: "Scene: Home", action: "scene_home", description: "Restore a comfortable occupancy scene" },
  { label: "Scene: Away", action: "scene_away", description: "Shift the room into energy-saving mode" },
  { label: "All On", action: "all_on", description: "Power every controllable device" },
  { label: "All Off", action: "all_off", description: "Shut down the whole ecosystem" },
];

const SCENE_ACTIONS: Array<{ label: string; action: HomeAction; description: string }> = [
  { label: "Good Morning", action: "scene_good_morning", description: "Wake the room with a brighter, active setup" },
  { label: "Home Mode", action: "scene_home", description: "Balanced everyday comfort" },
  { label: "Away Mode", action: "scene_away", description: "Lower energy use and secure the room" },
  { label: "Good Night", action: "scene_good_night", description: "Prepare the space for sleep" },
];

const COMFORT_ACTIONS: Array<{ label: string; action: HomeAction; description: string }> = [
  { label: "Lights On", action: "light_on", description: "Increase room visibility" },
  { label: "Lights Off", action: "light_off", description: "Create a dimmer atmosphere" },
  { label: "Fan On", action: "fan_on", description: "Start air circulation" },
  { label: "Fan Off", action: "fan_off", description: "Stop room airflow" },
  { label: "AC On", action: "ac_on", description: "Cool the room" },
  { label: "AC Off", action: "ac_off", description: "Stop cooling" },
];

const ACCESS_ACTIONS: Array<{ label: string; action: HomeAction; description: string }> = [
  { label: "Open Curtains", action: "curtain_open", description: "Let in more daylight" },
  { label: "Close Curtains", action: "curtain_close", description: "Reduce light and increase privacy" },
  { label: "Unlock Door", action: "door_unlock", description: "Release the entry lock" },
  { label: "Lock Door", action: "door_lock", description: "Secure the entry lock" },
];

const MEDIA_ACTIONS: Array<{ label: string; action: HomeAction; description: string }> = [
  { label: "TV On", action: "tv_on", description: "Bring media online" },
  { label: "TV Off", action: "tv_off", description: "Power down media" },
  { label: "All On", action: "all_on", description: "Enable every controllable device" },
  { label: "All Off", action: "all_off", description: "Shut down everything at once" },
];

const INITIAL_ROOM_DEVICES: RoomDevice[] = [
  { id: "light", label: "Lights", on: false, actionOn: "light_on", actionOff: "light_off", description: "Primary room illumination" },
  { id: "fan", label: "Fan", on: false, actionOn: "fan_on", actionOff: "fan_off", description: "Air circulation and comfort" },
  { id: "ac", label: "AC", on: false, actionOn: "ac_on", actionOff: "ac_off", description: "Climate cooling control" },
  { id: "tv", label: "TV", on: false, actionOn: "tv_on", actionOff: "tv_off", description: "Media and entertainment" },
  { id: "curtains", label: "Curtains", on: false, actionOn: "curtain_open", actionOff: "curtain_close", description: "Privacy and daylight" },
  { id: "door", label: "Door Lock", on: false, actionOn: "door_unlock", actionOff: "door_lock", description: "Entry safety control" },
];

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

const DashboardPanel = ({
  open,
  settings,
  orbState,
  assistantText,
  runtimeHint,
  lastTranscript,
  lastLanguage,
  lastEmotion,
  voiceSignal,
  backendHealth,
  homeAutomationEnabled,
  homeStatus,
  dashboardUpdatedAt,
  dashboardStatusMessage,
  onOpenChange,
  onRefresh,
}: DashboardPanelProps) => {
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [devices, setDevices] = useState<RoomDevice[]>(INITIAL_ROOM_DEVICES);

  const lastStatusEntries = useMemo(() => Object.entries(homeStatus?.last_status ?? {}), [homeStatus]);

  const entries: EntryView[] = useMemo(
    () =>
      lastStatusEntries.map(([key, value]) => {
        const group = inferEntityGroup(key);
        const state = describeState(value);
        return {
          key,
          value,
          group: group.label,
          icon: group.icon,
          stateLabel: state.label,
          toneClass: state.toneClass,
        };
      }),
    [lastStatusEntries],
  );

  const connected = homeStatus?.connected ?? false;
  const snapshotAgeLabel = formatSnapshotAge(homeStatus?.last_status_at ?? null);
  const snapshotAgeMs = homeStatus?.last_status_at ? Date.now() - new Date(homeStatus.last_status_at).getTime() : null;

  const categorySummary = useMemo(() => {
    const counts = new Map<string, number>();
    entries.forEach((entry) => counts.set(entry.group, (counts.get(entry.group) ?? 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [entries]);

  const activeEntries = useMemo(
    () =>
      entries.filter((entry) => {
        if (typeof entry.value === "boolean") return entry.value;
        if (typeof entry.value === "number") return entry.value > 0;
        if (typeof entry.value === "string") {
          const lower = entry.value.toLowerCase();
          return ["on", "open", "unlocked", "active", "connected", "true", "running", "occupied"].includes(lower);
        }
        return Array.isArray(entry.value) ? entry.value.length > 0 : !!entry.value;
      }),
    [entries],
  );

  const issueNotes = useMemo(() => {
    const issues: string[] = [];
    if (!connected) issues.push("MQTT broker is currently disconnected.");
    if (!homeStatus?.last_status) issues.push("No live status snapshot is available yet.");
    if (snapshotAgeMs !== null && snapshotAgeMs > 300_000) issues.push("Latest telemetry is stale and should be refreshed.");
    if (activeEntries.length === 0 && lastStatusEntries.length > 0) issues.push("Status payload is present, but no active room states were detected.");
    return issues;
  }, [activeEntries.length, connected, homeStatus?.last_status, lastStatusEntries.length, snapshotAgeMs]);

  const ecosystemScore = calculateEcosystemScore({
    connected,
    snapshotAgeMs,
    entryCount: lastStatusEntries.length,
    activeCount: activeEntries.length,
  });

  const summaryTone = ecosystemScore >= 80 ? "text-emerald-200/90" : ecosystemScore >= 55 ? "text-cyan-100/90" : "text-amber-100/90";

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await onRefresh();
      setActionMessage("Dashboard refreshed");
    } finally {
      setIsRefreshing(false);
    }
  };

  const runAdvancedAction = async (action: HomeAction) => {
    setActionMessage(`Sending ${action.replace(/_/g, " ")}...`);
    try {
      const result = await executeHomeAction(action);
      if (result.status !== "executed") {
        throw new Error(result.error ?? result.detail ?? `Action ${action} was not executed`);
      }

      setActionMessage(`Executed ${action.replace(/_/g, " ")}`);
      await onRefresh();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Failed to execute action");
    }
  };

  const toggleDevice = async (deviceId: string) => {
    const device = devices.find((item) => item.id === deviceId);
    if (!device) {
      return;
    }

    const nextAction = device.on ? device.actionOff : device.actionOn;
    setActionMessage(`Sending ${device.label.toLowerCase()} ${device.on ? "off" : "on"}...`);

    try {
      const result = await executeHomeAction(nextAction);
      if (result.status !== "executed") {
        throw new Error(result.error ?? result.detail ?? `Action ${nextAction} was not executed`);
      }

      setDevices((previous) => previous.map((item) => (item.id === deviceId ? { ...item, on: !item.on } : item)));
      setActionMessage(`${device.label} turned ${device.on ? "off" : "on"}`);
      await onRefresh();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : `Failed to control ${device.label}`);
    }
  };

  const copySnapshot = async () => {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(
          {
            backendHealth,
            homeAutomationEnabled,
            homeStatus,
            lastStatusEntries,
            dashboardUpdatedAt,
            dashboardStatusMessage,
          },
          null,
          2,
        ),
      );
      setActionMessage("Snapshot copied to clipboard");
    } catch {
      setActionMessage("Clipboard access is unavailable");
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-none border-l border-white/10 bg-black/70 p-0 text-[#EAEAEA] backdrop-blur-2xl sm:w-[94vw] sm:max-w-[860px] lg:max-w-[1100px] xl:max-w-[1220px]">
        <motion.div className="flex h-full flex-col" variants={panelVariants} initial="hidden" animate="show">
          <motion.div variants={itemVariants}>
            <SheetHeader className="border-b border-white/10 px-4 py-4 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <SheetTitle className="text-sm font-light tracking-[0.22em] text-[#EAEAEA] sm:text-base">Dashboard</SheetTitle>
                <SheetDescription className="mt-2 max-w-xl text-[11px] text-white/44 sm:text-[12px]">
                  Live room monitoring, ecosystem analysis, and advanced home automation diagnostics.
                </SheetDescription>
              </div>
              <button
                type="button"
                onClick={handleRefresh}
                disabled={isRefreshing}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-white/60 transition-colors duration-300 hover:border-cyan-300/30 hover:text-white/85 disabled:opacity-50 sm:text-[11px]"
              >
                <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
                Refresh
              </button>
            </div>
            </SheetHeader>
          </motion.div>

          <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:space-y-5 sm:px-6 sm:py-5 no-scrollbar">
            <motion.section variants={itemVariants} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <MetricCard icon={Cpu} label="Backend" value={backendHealth ?? "Checking..."} hint="API health" />
              <MetricCard icon={Home} label="Broker" value={homeStatus?.broker ?? "Unknown"} hint={connected ? "MQTT connected" : "MQTT disconnected"} />
              <MetricCard icon={BrainCircuit} label="AI Mode" value={settings.ai.responseMode} hint="Current routing" />
              <MetricCard icon={Signal} label="Orb State" value={orbState} hint={`Emotion ${lastEmotion} · ${lastLanguage}`} />
              <MetricCard icon={Waves} label="Voice Signal" value={`Vol ${Math.round(voiceSignal.volume * 100)}%`} hint={`Pitch ${Math.round(voiceSignal.pitch)}Hz`} />
              <MetricCard icon={Clock3} label="Snapshot Age" value={snapshotAgeLabel} hint={dashboardUpdatedAt ?? dashboardStatusMessage ?? "Waiting"} />
            </motion.section>

            <motion.section variants={itemVariants} className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="space-y-4 rounded-3xl border border-white/10 bg-white/[0.025] p-3 sm:p-4">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-white/38">
                  <Gauge className="h-4 w-4 text-cyan-100/75" /> Ecosystem Analysis
                </div>

                <div className="flex flex-col gap-3 rounded-2xl border border-white/8 bg-black/20 px-4 py-4 sm:flex-row sm:items-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-full border border-cyan-300/18 bg-cyan-300/10 sm:h-16 sm:w-16">
                    <span className={cn("text-lg font-light tracking-[0.2em] sm:text-xl", summaryTone)}>{ecosystemScore}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-light text-[#EAEAEA]">Room ecosystem score</p>
                    <p className="mt-1 text-[11px] leading-relaxed text-white/40">Evaluated from connectivity, telemetry freshness, active devices, and live room signals.</p>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/8">
                      <div className="h-full rounded-full bg-gradient-to-r from-cyan-300/70 via-cyan-200/70 to-emerald-200/70" style={{ width: `${ecosystemScore}%` }} />
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Connected Entities</p>
                    <p className="mt-2 text-2xl font-light text-[#EAEAEA]">{lastStatusEntries.length}</p>
                    <p className="mt-1 text-[11px] text-white/40">Telemetry points observed from the home status channel.</p>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Active Signals</p>
                    <p className="mt-2 text-2xl font-light text-[#EAEAEA]">{activeEntries.length}</p>
                    <p className="mt-1 text-[11px] text-white/40">Entities currently showing an active or engaged state.</p>
                  </div>
                </div>

                <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Operational Summary</p>
                    <span className={cn("text-[10px] uppercase tracking-[0.2em]", connected ? "text-emerald-200/80" : "text-amber-100/80")}>
                      {connected ? "Broker online" : "Broker offline"}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-white/78">
                    {connected
                      ? `ZARA is currently observing ${lastStatusEntries.length} live room signals across the connected ecosystem. The freshest packet arrived ${snapshotAgeLabel}.`
                      : "The dashboard can still analyze the last snapshot, but live MQTT connectivity is currently unavailable."}
                  </p>
                </div>

                <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Issue Notes</p>
                  <div className="mt-3 space-y-2">
                    {issueNotes.length ? (
                      issueNotes.map((issue) => (
                        <div key={issue} className="flex items-start gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2">
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-200/80" />
                          <p className="text-[11px] leading-relaxed text-white/72">{issue}</p>
                        </div>
                      ))
                    ) : (
                      <div className="flex items-start gap-2 rounded-xl border border-emerald-300/12 bg-emerald-300/6 px-3 py-2">
                        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-emerald-200/85" />
                        <p className="text-[11px] leading-relaxed text-emerald-50/85">The current ecosystem snapshot looks stable.</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-3xl border border-white/10 bg-white/[0.025] p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-white/38">
                    <Home className="h-4 w-4 text-cyan-100/75" /> Room Controls
                  </div>
                  <p className="mt-2 text-[11px] text-white/38">Moved off the home screen. These controls now live in the dashboard.</p>

                  <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {devices.map((device) => (
                      <div key={device.id} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-light text-[#EAEAEA]">{device.label}</p>
                            <p className="mt-1 text-[11px] text-white/38">{device.description}</p>
                          </div>
                          <Switch
                            checked={device.on}
                            onCheckedChange={() => void toggleDevice(device.id)}
                            className="data-[state=checked]:bg-cyan-300/85 data-[state=unchecked]:bg-white/15"
                          />
                        </div>
                        <div className="mt-3 flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/34">
                          <span>Status</span>
                          <span className={device.on ? "text-emerald-200/85" : "text-white/55"}>{device.on ? "On" : "Off"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <motion.section variants={itemVariants} className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.025] p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-white/38">
                    <Activity className="h-4 w-4 text-cyan-100/75" /> Room Profile
                  </div>

                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Observed Zones</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {categorySummary.length ? (
                        categorySummary.map(([label, count]) => (
                          <span key={label} className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-white/70">
                            {label} · {count}
                          </span>
                        ))
                      ) : (
                        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-white/55">
                          No live zones detected
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                    {entries.slice(0, 8).map((entry) => {
                      const GroupIcon = entry.icon;

                      return (
                        <div key={entry.key} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex min-w-0 items-start gap-3">
                              <div className="rounded-full border border-cyan-300/12 bg-cyan-300/8 p-2 text-cyan-100/85">
                                <GroupIcon className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-light text-[#EAEAEA]">{entry.key}</p>
                                <p className="mt-1 text-[10px] uppercase tracking-[0.22em] text-white/34">{entry.group}</p>
                              </div>
                            </div>
                            <span className={cn("shrink-0 text-[10px] uppercase tracking-[0.2em]", entry.toneClass)}>{entry.stateLabel}</span>
                          </div>
                          <p className="mt-3 break-words text-[11px] leading-relaxed text-white/55">{formatValue(entry.value)}</p>
                        </div>
                      );
                    })}
                  </div>
                </motion.section>

                <motion.section variants={itemVariants} className="space-y-4 rounded-3xl border border-white/10 bg-white/[0.025] p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-white/38">
                    <PlugZap className="h-4 w-4 text-cyan-100/75" /> More Options
                  </div>

                  <div className="space-y-3">
                    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Scenes</p>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {SCENE_ACTIONS.map((item) => (
                          <motion.button
                            key={item.action}
                            type="button"
                            whileHover={{ y: -2 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => void runAdvancedAction(item.action)}
                            className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.05] to-white/[0.02] p-3 text-left transition-colors duration-300 hover:border-cyan-300/25"
                          >
                            <p className="text-sm font-light text-[#EAEAEA]">{item.label}</p>
                            <p className="mt-1 text-[11px] leading-relaxed text-white/38">{item.description}</p>
                          </motion.button>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Comfort</p>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {COMFORT_ACTIONS.map((item) => (
                          <motion.button
                            key={item.action}
                            type="button"
                            whileHover={{ y: -2 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => void runAdvancedAction(item.action)}
                            className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.05] to-white/[0.02] p-3 text-left transition-colors duration-300 hover:border-cyan-300/25"
                          >
                            <p className="text-sm font-light text-[#EAEAEA]">{item.label}</p>
                            <p className="mt-1 text-[11px] leading-relaxed text-white/38">{item.description}</p>
                          </motion.button>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Access & Media</p>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {ACCESS_ACTIONS.map((item) => (
                          <motion.button
                            key={item.action}
                            type="button"
                            whileHover={{ y: -2 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => void runAdvancedAction(item.action)}
                            className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.05] to-white/[0.02] p-3 text-left transition-colors duration-300 hover:border-cyan-300/25"
                          >
                            <p className="text-sm font-light text-[#EAEAEA]">{item.label}</p>
                            <p className="mt-1 text-[11px] leading-relaxed text-white/38">{item.description}</p>
                          </motion.button>
                        ))}
                        {MEDIA_ACTIONS.map((item) => (
                          <motion.button
                            key={item.action}
                            type="button"
                            whileHover={{ y: -2 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => void runAdvancedAction(item.action)}
                            className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.05] to-white/[0.02] p-3 text-left transition-colors duration-300 hover:border-cyan-300/25"
                          >
                            <p className="text-sm font-light text-[#EAEAEA]">{item.label}</p>
                            <p className="mt-1 text-[11px] leading-relaxed text-white/38">{item.description}</p>
                          </motion.button>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <button
                        type="button"
                        onClick={copySnapshot}
                        className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-white/65 transition-colors duration-300 hover:border-cyan-300/25 hover:text-white/85"
                      >
                        Copy Snapshot
                      </button>
                      <button
                        type="button"
                        onClick={handleRefresh}
                        className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-white/65 transition-colors duration-300 hover:border-cyan-300/25 hover:text-white/85"
                      >
                        Refresh Analysis
                      </button>
                    </div>

                    <AnimatePresence initial={false}>
                      {actionMessage ? (
                        <motion.p
                          key={actionMessage}
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          className="text-[11px] text-white/44"
                        >
                          {actionMessage}
                        </motion.p>
                      ) : null}
                    </AnimatePresence>
                  </div>
                </motion.section>

                <motion.section variants={itemVariants} className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.025] p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-white/38">
                    <Sparkles className="h-4 w-4 text-cyan-100/75" /> Live Activity
                  </div>
                  <div className="space-y-3 text-sm font-light text-[#EAEAEA]">
                    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Assistant</p>
                      <p className="mt-2 leading-relaxed text-white/82">{assistantText || "No assistant response yet."}</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                      <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                        <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Transcript</p>
                        <p className="mt-2 leading-relaxed text-white/76">{lastTranscript || "Waiting for speech input."}</p>
                      </div>
                      <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                        <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Runtime</p>
                        <p className="mt-2 leading-relaxed text-white/76">{runtimeHint || "No active runtime message."}</p>
                      </div>
                    </div>
                    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[10px] uppercase tracking-[0.22em] text-white/34">Operative Settings</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-white/70">
                        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1">Mode: {settings.ai.responseMode}</span>
                        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1">Presence: {settings.mode.presence}</span>
                        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1">Loop: {settings.ai.continuousLoop ? "On" : "Off"}</span>
                        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1">Automation: {homeAutomationEnabled === null ? "Unknown" : homeAutomationEnabled ? "On" : "Off"}</span>
                      </div>
                    </div>
                  </div>
                </motion.section>
              </div>
            </motion.section>
          </div>
        </motion.div>
      </SheetContent>
    </Sheet>
  );
};

export default DashboardPanel;
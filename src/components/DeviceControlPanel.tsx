import React, { useState } from "react";
import { motion } from "framer-motion";
import { executeHomeAction, type HomeAction } from "@/lib/zara-api";

interface Device {
  id: string;
  label: string;
  on: boolean;
  actionOn: HomeAction;
  actionOff: HomeAction;
}

interface DeviceControlPanelProps {
  onStatusChange?: (message: string) => void;
}

const DeviceControlPanel = ({ onStatusChange }: DeviceControlPanelProps) => {
  const [devices, setDevices] = useState<Device[]>([
    { id: "light", label: "Light", on: false, actionOn: "light_on", actionOff: "light_off" },
    { id: "fan", label: "Fan", on: false, actionOn: "fan_on", actionOff: "fan_off" },
    { id: "ac", label: "AC", on: false, actionOn: "ac_on", actionOff: "ac_off" },
    { id: "tv", label: "TV", on: false, actionOn: "tv_on", actionOff: "tv_off" },
  ]);

  const handleToggleDevice = async (deviceId: string) => {
    const device = devices.find((d) => d.id === deviceId);
    if (!device) return;

    const action = device.on ? device.actionOff : device.actionOn;

    try {
      const result = await executeHomeAction(action);
      if (result.status !== "executed") {
        throw new Error(result.error ?? result.detail ?? `Action ${action} was not executed`);
      }

      setDevices((prev) =>
        prev.map((d) => (d.id === deviceId ? { ...d, on: !d.on } : d))
      );

      const status = device.on ? "off" : "on";
      const message = `${device.label} turned ${status}`;
      onStatusChange?.(message);
    } catch (error) {
      const message = error instanceof Error ? error.message : `Failed to control ${device.label}`;
      onStatusChange?.(message);
      console.error(`Failed to execute action ${action}:`, error);
    }
  };

  return (
    <div className="absolute left-6 top-20 z-20 w-44 rounded-lg bg-white/3 backdrop-blur-md p-3">
      <h4 className="text-xs font-semibold text-foreground/90">Home Devices</h4>
      <div className="mt-2 flex flex-col gap-2">
        {devices.map((d) => (
          <motion.div key={d.id} className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">{d.label}</div>
              <div className="text-xs text-muted-foreground/60">{d.on ? "On" : "Off"}</div>
            </div>
            <button
              onClick={() => handleToggleDevice(d.id)}
              className={`h-8 w-12 rounded-full transition-colors ${
                d.on ? "bg-emerald-400/80 hover:bg-emerald-500/80" : "bg-neutral-700/40 hover:bg-neutral-700/60"
              }`}
              aria-pressed={d.on}
            />
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default DeviceControlPanel;

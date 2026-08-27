import React, { useState, useEffect } from "react";
import { useUIStore } from "../store";
import { REGIONS, Region } from "../types";

interface CommandBarProps {
  defconLevel: number;
}

export const CommandBar: React.FC<CommandBarProps> = ({ defconLevel }) => {
  const { region, setRegion, showBrief, setShowBrief, showTv, setShowTv } = useUIStore();
  const [clock, setClock] = useState<string>("");

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(now.toUTCString().replace("GMT", "UTC"));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="cmdbar">
      <div className="cmd-left">
        <span className="cmd-globe">◍</span>
        <span className="cmd-word">WAR</span>
        <span className="cmd-sep">·</span>
        <span className="cmd-word cmd-accent">MONITOR</span>
        <span className="cmd-ver">v0.4.0</span>
      </div>
      <div className="cmd-right">
        <button
          className={`cmd-btn brief-btn ${showBrief ? "active" : ""}`}
          onClick={() => setShowBrief(true)}
        >
          <span className="brief-spark">✦</span> AI BRIEF
        </button>
        <button
          className={`cmd-btn tv-btn ${showTv ? "active" : ""}`}
          onClick={() => setShowTv(!showTv)}
        >
          <span className="tv-icon">📺</span> LIVE TV
        </button>
        <span className="live-ind">
          <i />
          LIVE
        </span>
        <select
          className="cmd-select"
          value={region}
          onChange={(e) => setRegion(e.target.value as Region)}
        >
          {REGIONS.map((r) => (
            <option key={r} value={r}>
              {r.replace("_", " ").toUpperCase()}
            </option>
          ))}
        </select>
        <span className={`defcon-badge dc-${defconLevel}`}>⚠ DEFCON {defconLevel}</span>
        <span className="cmd-clock">{clock}</span>
      </div>
    </header>
  );
};

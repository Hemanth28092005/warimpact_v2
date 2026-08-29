import { useState, useEffect } from 'react';
import { useUIStore } from '../store';
import type { Region } from '../types';
import { INDIAN_PORTS } from '../utils/geo';

interface CommandBarProps {
  defconLevel: number;
  clock?: string;
}

export function CommandBar({ defconLevel, clock: propClock }: CommandBarProps) {
  const [internalClock, setInternalClock] = useState<string>('');
  const {
    region,
    setRegion,
    showBrief,
    setShowBrief,
    showTv,
    setShowTv,
    showSage,
    setShowSage,
    selectedPort,
    setSelectedPort,
    mapRef,
  } = useUIStore();

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setInternalClock(now.toUTCString().replace('GMT', 'UTC'));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const clock = propClock || internalClock;

  return (
    <header className="cmdbar">
      <div className="cmd-left" title="S.A.G.E — Strategic Advisory & Geopolitical Evaluation">
        <span className="cmd-globe">◍</span>
        <span className="cmd-word">S·A·G·E</span>
        <span className="cmd-ver">v1.0</span>
      </div>
      <div className="cmd-right">
        <button
          className={`cmd-btn sage-btn ${showSage ? 'active' : ''}`}
          onClick={() => setShowSage(!showSage)}
          title="S.A.G.E AI — Strategic Advisory & Geopolitical Evaluation"
        >
          <span className="sage-spark">🤖</span> S.A.G.E AI
        </button>
        <button className={`cmd-btn brief-btn ${showBrief ? 'active' : ''}`} onClick={() => setShowBrief(true)}>
          <span className="brief-spark">✦</span> AI BRIEF
        </button>
        <button className={`cmd-btn tv-btn ${showTv ? 'active' : ''}`} onClick={() => setShowTv(!showTv)}>
          <span className="tv-icon">📺</span> LIVE TV
        </button>
        <span className="live-ind"><i />LIVE</span>
        <select className="cmd-select" value={region} onChange={(e) => setRegion(e.target.value as Region)}>
          {['usa', 'europe', 'middle_east', 'india'].map((r) => (
            <option key={r} value={r}>{r.replace('_', ' ').toUpperCase()}</option>
          ))}
        </select>
        <select
          className="cmd-select port-select-header"
          value={selectedPort}
          onChange={(e) => {
            const pCode = e.target.value;
            setSelectedPort(pCode);
            if (pCode !== 'ALL') {
              const portObj = INDIAN_PORTS.find((p) => p.code === pCode);
              if (portObj && mapRef) {
                mapRef.flyTo({ center: [portObj.long, portObj.lat], zoom: 5.2, pitch: 35 });
              }
            } else if (mapRef) {
              mapRef.flyTo({ center: [78.9629, 20.5937], zoom: 3.5, pitch: 20 });
            }
          }}
          style={{
            background: selectedPort !== 'ALL' ? '#0284c7' : '#0a152e',
            borderColor: selectedPort !== 'ALL' ? '#38bdf8' : '#1e3a8a',
            color: '#f8fafc',
            fontWeight: 600,
          }}
          title="Filter Trade Routes by Port"
        >
          <option value="ALL">⚓ PORT: ALL PORTS</option>
          {INDIAN_PORTS.map((p) => (
            <option key={p.code} value={p.code}>
              ⚓ {p.name.replace(' Port', '')} ({p.state})
            </option>
          ))}
        </select>
        <span className={`defcon-badge dc-${defconLevel}`}>⚠ DEFCON {defconLevel}</span>
        <span className="cmd-clock">{clock}</span>
      </div>
    </header>
  );
}

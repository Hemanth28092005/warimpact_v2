import { useEffect, useState } from 'react';
import { useUIStore } from '../store';
import type { Alert } from '../types';

const HERO_MESSAGES = [
  "INDIA'S TRADE AT RISK: 13 CHOKEPOINTS, $480B EXPOSURE",
  "AI-POWERED GEOPOLITICAL INSTABILITY INDEX — 38 COUNTRIES, DAILY",
  "CASCADE DETECTION: WHEN ONE COUNTRY SPIKES, WHO'S NEXT?",
  "REAL-TIME: MILITARY FLIGHTS • SEISMIC • CHOKEPOINTS • MARKETS",
];

interface HeroBannerProps {
  onDismiss?: () => void;
  alerts: Alert[];
  avgCii: number | null;
  defconLevel: number;
}

export function HeroBanner({ onDismiss, alerts, avgCii, defconLevel }: HeroBannerProps) {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % HERO_MESSAGES.length);
    }, 4000);

    const hideTimer = setTimeout(() => setVisible(false), 12000);

    return () => {
      clearInterval(timer);
      clearTimeout(hideTimer);
    };
  }, []);

  if (!visible) return null;

  return (
    <div className="hero-banner" onClick={() => { onDismiss?.(); setVisible(false); }}>
      <span className="hero-icon">⚡</span>
      <span className="hero-text">{HERO_MESSAGES[index]}</span>
      <button className="hero-dismiss" onClick={(e) => { e.stopPropagation(); onDismiss?.(); setVisible(false); }}>
        ✕
      </button>
    </div>
  );
}
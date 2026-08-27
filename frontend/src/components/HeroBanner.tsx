import React from "react";
import { Alert } from "../types";
import { timeAgo } from "../utils/formatters";

interface HeroBannerProps {
  alerts: Alert[];
  avgCii: number | null;
  defconLevel: number;
}

export const HeroBanner: React.FC<HeroBannerProps> = ({
  alerts,
  avgCii,
  defconLevel,
}) => {
  const topCriticalAlert = alerts.find((a) => a.level === "critical") || alerts[0];

  if (!topCriticalAlert) return null;

  return (
    <div className="hero-banner">
      <div className="hero-banner-inner">
        <div className="hero-status-pill">
          <span className={`hero-pulse-dot dc-${defconLevel}`} />
          <span className="hero-status-text">DEFCON {defconLevel} ACTIVE</span>
        </div>
        <div className="hero-content">
          <span className="hero-badge">FLASH ADVISORY</span>
          <span className="hero-entity">{topCriticalAlert.entity}:</span>
          <span className="hero-message">{topCriticalAlert.message}</span>
        </div>
        <div className="hero-meta">
          <span className="hero-time">{timeAgo(topCriticalAlert.timestamp)}</span>
          {avgCii !== null && (
            <span className="hero-cii-val">
              AVG CII: <b>{avgCii.toFixed(1)}</b>/100
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

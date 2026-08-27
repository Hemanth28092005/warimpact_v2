import React, { useState } from "react";
import { Alert } from "../types";
import { timeAgo } from "../utils/formatters";

interface AlertsPanelProps {
  alerts: Alert[];
  onClose?: () => void;
}

export const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts, onClose }) => {
  const [filter, setFilter] = useState<"all" | "critical" | "warning">("all");

  const filteredAlerts = alerts.filter((a) => {
    if (filter === "all") return true;
    return a.level === filter;
  });

  return (
    <div className="alerts-modal">
      <div className="alerts-head">
        <div className="alerts-title-block">
          <span className="alerts-dot" />
          <span className="alerts-title">SYSTEMIC RISK & CRISIS ALERTS</span>
          <span className="alerts-count">({filteredAlerts.length})</span>
        </div>
        <div className="alerts-filters">
          <button
            className={`af-btn ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            ALL
          </button>
          <button
            className={`af-btn crit ${filter === "critical" ? "active" : ""}`}
            onClick={() => setFilter("critical")}
          >
            CRITICAL
          </button>
          <button
            className={`af-btn warn ${filter === "warning" ? "active" : ""}`}
            onClick={() => setFilter("warning")}
          >
            WARNING
          </button>
          {onClose && (
            <button className="af-close" onClick={onClose}>
              ✕
            </button>
          )}
        </div>
      </div>

      <div className="alerts-list">
        {filteredAlerts.length === 0 ? (
          <div className="alerts-empty">No active alerts for current filter criteria.</div>
        ) : (
          filteredAlerts.map((a) => (
            <div key={a.id} className={`alert-card lvl-${a.level}`}>
              <div className="ac-top">
                <span className={`ac-tag lvl-${a.level}`}>{a.type.toUpperCase()}</span>
                <span className="ac-entity">{a.entity}</span>
                <span className="ac-time">{timeAgo(a.timestamp)}</span>
              </div>
              <div className="ac-msg">{a.message}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

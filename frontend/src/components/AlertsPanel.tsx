import { useUIStore } from '../store';
import type { Alert } from '../types';

export function AlertsPanel() {
  const { alerts, clearAlerts } = useUIStore();

  if (alerts.length === 0) return null;

  return (
    <div className="alerts-panel">
      <div className="alerts-header">
        <span className="alerts-title">⚠ LIVE ALERTS</span>
        <button className="alerts-clear" onClick={clearAlerts}>CLEAR</button>
      </div>
      <div className="alerts-list">
        {alerts.slice(0, 8).map((alert: Alert) => (
          <div key={alert.id} className={`alert-item alert-${alert.level}`}>
            <span className="alert-dot" />
            <div className="alert-content">
              <span className="alert-message">{alert.message}</span>
              <span className="alert-meta">
                {alert.entity} · {alert.type.toUpperCase()} · {new Date(alert.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <span className={`alert-badge alert-${alert.level}`}>
              {alert.level.toUpperCase()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
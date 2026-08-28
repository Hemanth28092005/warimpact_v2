import { useUIStore } from '../store';
import type { Region, MapTheme, Commodity } from '../types';
import { REGIONS, WINDOWS_H } from '../types';
import { fmtPct } from '../utils/format';

interface SitBarProps {
  escalationsCount: number;
  govActionsCount: number;
  flightsCount: number;
  chokeAlertsCount: number;
  commodities: Commodity[];
}

export function SitBar({ escalationsCount, govActionsCount, flightsCount, chokeAlertsCount, commodities }: SitBarProps) {
  const { 
    region, setRegion, windowH, setWindowH,
    mapTheme, setMapTheme, view3d, setView3d, autoRotate, setAutoRotate
  } = useUIStore();

  return (
    <div className="sitbar">
      <span>GLOBAL SITUATION</span>
      <span className="sit-center">
        {escalationsCount} ESCALATIONS · {govActionsCount} GOV POLICIES · {flightsCount} MIL AIRBORNE · {chokeAlertsCount} CHOKE ALERTS
      </span>
      <span className="sit-right">
        {commodities.slice(0, 3).map((c) => (
          <span key={c.commodity_code} className="sit-tick">
            {c.name.split(' ')[0].toUpperCase()}{' '}
            <b className={(c.change_pct ?? 0) >= 0 ? 'up' : 'down'}>{fmtPct(c.change_pct)}</b>
          </span>
        ))}
        <span className="view-toggle">
          <button className={mapTheme === 'satellite' ? 'vt active' : 'vt'} onClick={() => setMapTheme('satellite')} title="Photorealistic Satellite & Bathymetry Earth">SAT</button>
          <button className={mapTheme === 'dark' ? 'vt active' : 'vt'} onClick={() => setMapTheme('dark')} title="Dark Cyber Tactical Matrix">DARK</button>
        </span>
        <span className="view-toggle">
          <button className={!view3d ? 'vt active' : 'vt'} onClick={() => setView3d(false)}>2D</button>
          <button className={view3d ? 'vt active' : 'vt'} onClick={() => setView3d(true)}>3D</button>
        </span>
        <button className={`orbit-btn ${autoRotate ? 'active' : ''}`} onClick={() => setAutoRotate(!autoRotate)} title="Auto-rotate Globe Orbit">↻ ORBIT</button>
        <div className="win-chips">
          {WINDOWS_H.map((h) => (
            <button key={h} className={windowH === h ? 'chip active' : 'chip'} onClick={() => setWindowH(h)}>
              {h === 168 ? '7d' : `${h}h`}
            </button>
          ))}
        </div>
      </span>
    </div>
  );
}
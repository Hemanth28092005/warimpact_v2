import { useUIStore } from '../store';
import type { Chokepoint, TradeRoute, AggressionPair, CascadePair } from '../types';
import { timeAgo } from '../utils/format';
import { CASCADE_COUNTRIES } from '../types';

interface Panel2Props {
  scoresArr: [string, number][];
  chokepoints: Chokepoint[];
  aggression: AggressionPair[];
  cascade: CascadePair[];
  routes: TradeRoute[];
}

export function Panel2({ scoresArr, chokepoints, aggression, cascade, routes }: Panel2Props) {
  const { cascadeCountry, setCascadeCountry, p2, setP2, mapRef } = useUIStore();

  const topAggression = aggression
    .filter((p) => p.aggression_score !== null && p.data_source === 'gdelt_derived')
    .sort((a, b) => (b.aggression_score ?? 0) - (a.aggression_score ?? 0))
    .slice(0, 14);
  const topRoutes = [...routes].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <section className="bp">
      <div className="bp-head">
        <span>STRATEGIC RISK INTEL</span>
        <span className="bp-count">38 SCOPE</span>
      </div>
      <div className="bp-tabs">
        {(['cii', 'chokepoints', 'aggression', 'cascade', 'routes'] as const).map((t) => (
          <button key={t} className={p2 === t ? 'btab active' : 'btab'} onClick={() => setP2(t)}>
            {t === 'cii' ? 'CII' : t === 'chokepoints' ? 'CHOKEPOINTS' : t.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="bp-list">
        {p2 === 'cii' && (
          <>
            {scoresArr.slice(0, 14).map(([code, score]) => (
              <div key={code} className="row">
                <span className={`sev-tag ${score >= 70 ? 'crit' : score >= 50 ? 'high' : score >= 30 ? 'mid' : 'pos'}`}>{score.toFixed(0)}</span>
                <span className="row-main">
                  <span className="row-title">{code}</span>
                  <span className="cii-bar"><i style={{ width: `${score}%` }} className={score >= 70 ? 'crit' : score >= 50 ? 'high' : 'mid'} /></span>
                </span>
              </div>
            ))}
            {scoresArr.length === 0 && <div className="empty">// awaiting CII scores</div>}
          </>
        )}

        {p2 === 'chokepoints' && (
          <>
            {chokepoints.map((cp: Chokepoint) => (
              <div
                key={cp.code}
                className="row row-clickable"
                onClick={() => mapRef?.flyTo({ center: [cp.long, cp.lat], zoom: 5 })}
              >
                <span className={`sev-tag ${cp.status === 'red' ? 'crit' : cp.status === 'yellow' ? 'high' : 'pos'}`}>{cp.disruption_score.toFixed(0)}</span>
                <span className="row-main">
                  <span className="row-title">{cp.name} ({cp.code}) · <b className={cp.status === 'red' ? 'down' : cp.status === 'yellow' ? 'up' : 'pos'}>{cp.status.toUpperCase()}</b></span>
                  <span className="row-sub">{cp.baseline_mbd} MBD baseline · {cp.last_disruption_reason || 'Normal transit'}</span>
                </span>
              </div>
            ))}
            {chokepoints.length === 0 && <div className="empty">// awaiting chokepoints data</div>}
          </>
        )}

        {p2 === 'aggression' && (
          <>
            {topAggression.map((p: AggressionPair) => (
              <div key={`${p.country_a}-${p.country_b}`} className="row">
                <span className={`sev-tag ${(p.aggression_score ?? 0) >= 70 ? 'crit' : (p.aggression_score ?? 0) >= 40 ? 'high' : 'mid'}`}>{(p.aggression_score ?? 0).toFixed(0)}</span>
                <span className="row-main">
                  <span className="row-title">{p.country_a} → {p.country_b}</span>
                  <span className="row-sub">{p.event_count} events · 365d window</span>
                </span>
              </div>
            ))}
            {topAggression.length === 0 && <div className="empty">// no aggression data</div>}
          </>
        )}

        {p2 === 'cascade' && (
          <>
            <div className="inline-select">
              <select className="cmd-select" value={cascadeCountry} onChange={(e) => setCascadeCountry(e.target.value)}>
                {CASCADE_COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <span className="row-sub">contagion source · 7d window</span>
            </div>
            {cascade.slice(0, 12).map((p: CascadePair) => {
              const other = p.source_country === cascadeCountry ? p.target_country : p.source_country;
              return (
                <div key={`${p.source_country}-${p.target_country}`} className="row">
                  <span className={`sev-tag ${p.contagion_score >= 0.6 ? 'crit' : p.contagion_score >= 0.3 ? 'high' : 'mid'}`}>
                    {(p.contagion_score * 100).toFixed(0)}%
                  </span>
                  <span className="row-main">
                    <span className="row-title">{cascadeCountry} ⇄ {other}</span>
                    <span className="row-sub">{p.co_spike_count}/{p.source_spike_count} co-spikes</span>
                  </span>
                </div>
              );
            })}
            {cascade.length === 0 && <div className="empty">// no cascade pairs for {cascadeCountry}</div>}
          </>
        )}

        {p2 === 'routes' && (
          <>
            {topRoutes.slice(0, 14).map((r: TradeRoute) => (
              <div
                key={r.id}
                className="row row-clickable"
                onClick={() => mapRef?.flyTo({ center: [r.origin_long, r.origin_lat], zoom: 4 })}
              >
                <span className={`sev-tag ${r.risk_score >= 70 ? 'crit' : r.risk_score >= 45 ? 'high' : 'mid'}`}>{r.risk_score.toFixed(0)}</span>
                <span className="row-main">
                  <span className="row-title">{r.commodity_code} · IND → {r.partner_country}</span>
                  <span className="row-sub">via {r.primary_chokepoint ?? 'direct lane'}</span>
                </span>
              </div>
            ))}
            {topRoutes.length === 0 && <div className="empty">// no trade routes ingested</div>}
          </>
        )}
      </div>
    </section>
  );
}
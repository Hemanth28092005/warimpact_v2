import { useUIStore } from '../store';
import type { Prediction, Headline, Commodity, Freight, Flight, NavalFleet, Quake } from '../types';
import { timeAgo, fmtPct } from '../utils/format';
import { HEADLINE_REGIONS } from '../types';

interface Panel3Props {
  predictions: Prediction[];
  headlines: Headline[];
  commodities: Commodity[];
  freight: Freight[];
  flights: Flight[];
  navalFleets?: NavalFleet[];
  quakesNear: Quake[];
}

export function Panel3({ predictions, headlines, commodities, freight, flights, navalFleets = [], quakesNear }: Panel3Props) {
  const { headlineRegion, setHeadlineRegion, p3, setP3, mapRef } = useUIStore();

  return (
    <section className="bp">
      <div className="bp-head">
        <span>SIGNALS & MARKETS</span>
        <span className="bp-count">
          {p3 === 'odds'
            ? predictions.length
            : p3 === 'headlines'
            ? headlines.length
            : p3 === 'markets'
            ? commodities.length + freight.length
            : p3 === 'flights'
            ? flights.length
            : p3 === 'fleets'
            ? navalFleets.length
            : quakesNear.length}
        </span>
      </div>
      <div className="bp-tabs">
        {(['odds', 'headlines', 'markets', 'flights', 'fleets', 'seismic'] as const).map((t) => (
          <button key={t} className={p3 === t ? 'btab active' : 'btab'} onClick={() => setP3(t)}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="bp-list">
        {p3 === 'odds' && (
          <>
            {predictions.slice(0, 10).map((m: Prediction) => (
              <a key={m.market_slug} className="row" href={m.url ?? '#'} target="_blank" rel="noreferrer">
                <span className={`sev-tag ${(m.yes_price ?? 0) >= 0.5 ? 'crit' : 'mid'}`}>{m.yes_price !== null ? `${(m.yes_price * 100).toFixed(0)}%` : '—'}</span>
                <span className="row-main">
                  <span className="row-title clamp2">{m.question}</span>
                  <span className="row-sub">polymarket · ${(m.volume_24h_usd ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}/24h</span>
                </span>
              </a>
            ))}
            {predictions.length === 0 && <div className="empty">// no open markets</div>}
          </>
        )}

        {p3 === 'headlines' && (
          <>
            <div className="inline-select">
              <select className="cmd-select" value={headlineRegion} onChange={(e) => setHeadlineRegion(e.target.value)}>
                {HEADLINE_REGIONS.map((r) => <option key={r} value={r}>{r.replace(/_/g, ' ').toUpperCase()}</option>)}
              </select>
            </div>
            {headlines.map((h: Headline) => (
              <a key={h.id} className="row" href={h.source_url ?? '#'} target="_blank" rel="noreferrer">
                <span className="sev-tag mid">#{h.rank}</span>
                <span className="row-main">
                  <span className="row-title clamp2">{h.headline}</span>
                  {h.llm_brief && <span className="row-sub clamp2">{h.llm_brief}</span>}
                </span>
              </a>
            ))}
            {headlines.length === 0 && <div className="empty">// no headlines for region</div>}
          </>
        )}

        {p3 === 'markets' && (
          <>
            <div className="tab-section-head">TRACKED COMMODITIES</div>
            {commodities.map((c: Commodity) => (
              <div key={c.commodity_code} className="row">
                <span className={`sev-tag ${(c.change_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>{fmtPct(c.change_pct)}</span>
                <span className="row-main">
                  <span className="row-title">{c.name}</span>
                  <span className="row-sub">${c.price_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })} USD</span>
                </span>
              </div>
            ))}
            <div className="tab-section-head" style={{ marginTop: 8 }}>GLOBAL FREIGHT INDICES</div>
            {freight.map((fr: Freight) => (
              <div key={fr.index_code} className="row">
                <span className={`sev-tag ${(fr.change_pct ?? 0) >= 0 ? 'high' : 'pos'}`}>{fmtPct(fr.change_pct)}</span>
                <span className="row-main">
                  <span className="row-title">{fr.name}</span>
                  <span className="row-sub">${fr.rate_usd.toLocaleString()} / FEU {fr.is_estimated ? '(est)' : ''}</span>
                </span>
              </div>
            ))}
          </>
        )}

        {p3 === 'flights' && (
          <>
            {flights.slice(0, 14).map((fl: Flight) => (
              <div
                key={fl.hex}
                className="row row-clickable"
                onClick={() => mapRef?.flyTo({ center: [fl.longitude, fl.latitude], zoom: 6 })}
              >
                <span className="sev-tag mid">{fl.aircraft_type ?? 'MIL'}</span>
                <span className="row-main">
                  <span className="row-title">{fl.callsign || fl.hex} · {fl.registration || 'No Reg'}</span>
                  <span className="row-sub">
                    {fl.altitude_ft ? `${fl.altitude_ft.toLocaleString()} ft` : 'ground'} · {fl.ground_speed_kt ? `${fl.ground_speed_kt.toFixed(0)} kt` : '—'} · sq {fl.squawk || '—'}
                  </span>
                </span>
              </div>
            ))}
            {flights.length === 0 && <div className="empty">// no military flights active</div>}
          </>
        )}

        {p3 === 'fleets' && (
          <>
            {navalFleets.map((fleet: NavalFleet) => (
              <div
                key={fleet.code}
                className="row row-clickable"
                onClick={() => mapRef?.flyTo({ center: [fleet.longitude, fleet.latitude], zoom: 5 })}
              >
                <span className={`sev-tag ${fleet.threat_level === 'critical' ? 'crit' : fleet.threat_level === 'elevated' ? 'high' : 'mid'}`}>
                  {fleet.country_code}
                </span>
                <span className="row-main">
                  <span className="row-title clamp2">{fleet.name}</span>
                  <span className="row-sub clamp2">
                    ⚓ {fleet.flagship} · {fleet.operational_area} · {fleet.status.toUpperCase()}
                  </span>
                </span>
              </div>
            ))}
            {navalFleets.length === 0 && <div className="empty">// no strategic naval fleets tracked</div>}
          </>
        )}

        {p3 === 'seismic' && (
          <>
            {quakesNear.slice(0, 10).map((q: Quake) => (
              <div
                key={q.external_id}
                className="row row-clickable"
                onClick={() => mapRef?.flyTo({ center: [q.longitude, q.latitude], zoom: 6 })}
              >
                <span className="sev-tag mid">M{q.magnitude.toFixed(1)}</span>
                <span className="row-main">
                  <span className="row-title clamp2">{q.place ?? '—'}</span>
                  <span className="row-sub">{q.near_chokepoint_code} · {q.distance_to_chokepoint_km?.toFixed(0)}km · {timeAgo(q.occurred_at)} ago</span>
                </span>
              </div>
            ))}
            {quakesNear.length === 0 && <div className="empty">// no quakes near chokepoints</div>}
          </>
        )}
      </div>
    </section>
  );
}
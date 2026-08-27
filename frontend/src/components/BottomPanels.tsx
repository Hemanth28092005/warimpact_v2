import React from "react";
import { useUIStore } from "../store";
import {
  FeedItem,
  GovernmentAction,
  Protest,
  Chokepoint,
  AggressionPair,
  CascadePair,
  TradeRoute,
  Prediction,
  Headline,
  Commodity,
  Freight,
  Flight,
  Quake,
  CASCADE_COUNTRIES,
  HEADLINE_REGIONS,
} from "../types";
import { fmtPct, timeAgo } from "../utils/formatters";

interface BottomPanelsProps {
  feed: FeedItem[];
  govActions: GovernmentAction[];
  protests: Protest[];
  scoresArr: [string, number][];
  chokepoints: Chokepoint[];
  topAggression: AggressionPair[];
  cascade: CascadePair[];
  topRoutes: TradeRoute[];
  predictions: Prediction[];
  headlines: Headline[];
  commodities: Commodity[];
  freight: Freight[];
  flights: Flight[];
  quakesNear: Quake[];
  onFlyToLocation?: (coords: [number, number], zoom?: number) => void;
}

export const BottomPanels: React.FC<BottomPanelsProps> = ({
  feed,
  govActions,
  protests,
  scoresArr,
  chokepoints,
  topAggression,
  cascade,
  topRoutes,
  predictions,
  headlines,
  commodities,
  freight,
  flights,
  quakesNear,
  onFlyToLocation,
}) => {
  const {
    p1,
    setP1,
    p2,
    setP2,
    p3,
    setP3,
    cascadeCountry,
    setCascadeCountry,
    headlineRegion,
    setHeadlineRegion,
  } = useUIStore();

  return (
    <div className="bottom-row">
      {/* Panel 1: Live Escalations, Government Actions & Civil Unrest */}
      <section className="bp">
        <div className="bp-head">
          <span>PUBLIC & POLICY ACTIONS</span>
          <span className="bp-count">
            {p1 === "escalations"
              ? feed.length
              : p1 === "gov_actions"
              ? govActions.length
              : Math.min(12, protests.length)}
          </span>
        </div>
        <div className="bp-tabs">
          <button
            className={p1 === "escalations" ? "btab active" : "btab"}
            onClick={() => setP1("escalations")}
          >
            ESCALATIONS
          </button>
          <button
            className={p1 === "gov_actions" ? "btab active" : "btab"}
            onClick={() => setP1("gov_actions")}
          >
            GOV ACTIONS ({govActions.length})
          </button>
          <button
            className={p1 === "protests" ? "btab active" : "btab"}
            onClick={() => setP1("protests")}
          >
            CIVIL UNREST ({Math.min(12, protests.length)})
          </button>
        </div>
        <div className="bp-list">
          {p1 === "escalations" && (
            <>
              {feed.length === 0 && <div className="empty">// no escalations in window</div>}
              {feed.slice(0, 14).map((f) => (
                <a
                  key={f.global_event_id}
                  className="row"
                  href={f.source_url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className={`sev-tag ${f.event_severity <= -3 ? "crit" : "high"}`}>
                    {f.event_severity.toFixed(1)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">
                      {f.actor1_code ?? "—"} → {f.actor2_code ?? "—"} · {f.country_code ?? "—"}
                    </span>
                    <span className="row-sub">
                      {f.num_mentions} mentions · {timeAgo(f.ingested_at ?? f.event_date)}
                    </span>
                  </span>
                </a>
              ))}
            </>
          )}

          {p1 === "gov_actions" && (
            <>
              {govActions.length === 0 && (
                <div className="empty">// no government actions recorded</div>
              )}
              {govActions.map((g) => (
                <a
                  key={g.rank}
                  className="row"
                  href={g.source_url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span
                    className={`sev-tag ${
                      g.action_type === "diplomatic"
                        ? "pos"
                        : g.action_type === "security"
                        ? "crit"
                        : g.action_type === "fiscal"
                        ? "high"
                        : "mid"
                    }`}
                  >
                    {g.action_type ? g.action_type.toUpperCase().slice(0, 7) : "GOV"}
                  </span>
                  <span className="row-main">
                    <span className="row-title clamp2">
                      #{g.rank} · {g.headline}
                    </span>
                    {g.llm_brief && <span className="row-sub clamp2">{g.llm_brief}</span>}
                    {g.published_at && (
                      <span className="row-sub">{timeAgo(g.published_at)}</span>
                    )}
                  </span>
                </a>
              ))}
            </>
          )}

          {p1 === "protests" && (
            <>
              {protests.length === 0 && (
                <div className="empty">// no civil unrest recorded</div>
              )}
              {protests.slice(0, 12).map((p) => (
                <a
                  key={p.id}
                  className="row"
                  href={p.source_url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span
                    className={`sev-tag ${
                      p.event_severity >= 80 ? "crit" : p.event_severity >= 60 ? "high" : "mid"
                    }`}
                  >
                    {p.location_name
                      ? p.location_name.toUpperCase().slice(0, 8)
                      : p.city
                      ? p.city.toUpperCase().slice(0, 8)
                      : "UNREST"}
                  </span>
                  <span className="row-main">
                    <span className="row-title clamp2">{p.headline}</span>
                    {p.llm_brief && <span className="row-sub clamp2">{p.llm_brief}</span>}
                    <span className="row-sub">
                      {p.location_level ? `[${p.location_level.toUpperCase()}] ` : ""}
                      {p.location_name && p.location_name !== p.city ? `${p.location_name}, ` : ""}
                      {p.state ? `${p.state} · ` : ""}
                      {p.event_date} · Sev: {p.event_severity.toFixed(0)}/100
                      {p.validation_source ? ` · (${p.validation_source.toUpperCase()})` : ""}
                    </span>
                  </span>
                </a>
              ))}
            </>
          )}
        </div>
      </section>

      {/* Panel 2: Risk Intel, Chokepoints, Aggression, Cascade & Routes */}
      <section className="bp">
        <div className="bp-head">
          <span>STRATEGIC RISK INTEL</span>
          <span className="bp-count">38 SCOPE</span>
        </div>
        <div className="bp-tabs">
          {(["cii", "chokepoints", "aggression", "cascade", "routes"] as const).map((t) => (
            <button
              key={t}
              className={p2 === t ? "btab active" : "btab"}
              onClick={() => setP2(t)}
            >
              {t === "cii" ? "CII" : t === "chokepoints" ? "CHOKEPOINTS" : t.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="bp-list">
          {p2 === "cii" && (
            <>
              {scoresArr.slice(0, 14).map(([code, score]) => (
                <div key={code} className="row">
                  <span
                    className={`sev-tag ${
                      score >= 70 ? "crit" : score >= 50 ? "high" : score >= 30 ? "mid" : "pos"
                    }`}
                  >
                    {score.toFixed(0)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">{code}</span>
                    <span className="cii-bar">
                      <i
                        style={{ width: `${score}%` }}
                        className={score >= 70 ? "crit" : score >= 50 ? "high" : "mid"}
                      />
                    </span>
                  </span>
                </div>
              ))}
              {scoresArr.length === 0 && <div className="empty">// awaiting CII scores</div>}
            </>
          )}

          {p2 === "chokepoints" && (
            <>
              {chokepoints.map((cp) => (
                <div
                  key={cp.code}
                  className="row row-clickable"
                  onClick={() => onFlyToLocation?.([cp.long, cp.lat], 5)}
                >
                  <span
                    className={`sev-tag ${
                      cp.status === "critical"
                        ? "crit"
                        : cp.status === "elevated"
                        ? "high"
                        : "pos"
                    }`}
                  >
                    {cp.disruption_score.toFixed(0)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">
                      {cp.name} ({cp.code}) ·{" "}
                      <b
                        className={
                          cp.status === "critical"
                            ? "down"
                            : cp.status === "elevated"
                            ? "up"
                            : "pos"
                        }
                      >
                        {cp.status.toUpperCase()}
                      </b>
                    </span>
                    <span className="row-sub">
                      {cp.baseline_mbd} MBD baseline ·{" "}
                      {cp.last_disruption_reason || "Normal transit"}
                    </span>
                  </span>
                </div>
              ))}
              {chokepoints.length === 0 && (
                <div className="empty">// awaiting chokepoints data</div>
              )}
            </>
          )}

          {p2 === "aggression" && (
            <>
              {topAggression.map((p) => (
                <div key={`${p.country_a}-${p.country_b}`} className="row">
                  <span
                    className={`sev-tag ${
                      (p.aggression_score ?? 0) >= 70
                        ? "crit"
                        : (p.aggression_score ?? 0) >= 40
                        ? "high"
                        : "mid"
                    }`}
                  >
                    {(p.aggression_score ?? 0).toFixed(0)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">
                      {p.country_a} → {p.country_b}
                    </span>
                    <span className="row-sub">{p.event_count} events · 365d window</span>
                  </span>
                </div>
              ))}
              {topAggression.length === 0 && <div className="empty">// no aggression data</div>}
            </>
          )}

          {p2 === "cascade" && (
            <>
              <div className="inline-select">
                <select
                  className="cmd-select"
                  value={cascadeCountry}
                  onChange={(e) => setCascadeCountry(e.target.value)}
                >
                  {CASCADE_COUNTRIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <span className="row-sub">contagion source · 7d window</span>
              </div>
              {cascade.slice(0, 12).map((p) => {
                const other =
                  p.source_country === cascadeCountry ? p.target_country : p.source_country;
                return (
                  <div key={`${p.source_country}-${p.target_country}`} className="row">
                    <span
                      className={`sev-tag ${
                        p.contagion_score >= 0.6
                          ? "crit"
                          : p.contagion_score >= 0.3
                          ? "high"
                          : "mid"
                      }`}
                    >
                      {(p.contagion_score * 100).toFixed(0)}%
                    </span>
                    <span className="row-main">
                      <span className="row-title">
                        {cascadeCountry} ⇄ {other}
                      </span>
                      <span className="row-sub">
                        {p.co_spike_count}/{p.source_spike_count} co-spikes
                      </span>
                    </span>
                  </div>
                );
              })}
              {cascade.length === 0 && (
                <div className="empty">// no cascade pairs for {cascadeCountry}</div>
              )}
            </>
          )}

          {p2 === "routes" && (
            <>
              {topRoutes.slice(0, 14).map((r) => (
                <div
                  key={r.id}
                  className="row row-clickable"
                  onClick={() => onFlyToLocation?.([r.origin_long, r.origin_lat], 4)}
                >
                  <span
                    className={`sev-tag ${
                      r.risk_score >= 70 ? "crit" : r.risk_score >= 45 ? "high" : "mid"
                    }`}
                  >
                    {r.risk_score.toFixed(0)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">
                      {r.commodity_code} · IND → {r.partner_country}
                    </span>
                    <span className="row-sub">
                      via {r.primary_chokepoint ?? "direct lane"}
                    </span>
                  </span>
                </div>
              ))}
              {topRoutes.length === 0 && (
                <div className="empty">// no trade routes ingested</div>
              )}
            </>
          )}
        </div>
      </section>

      {/* Panel 3: Signals, News, Markets, Flights & Seismic */}
      <section className="bp">
        <div className="bp-head">
          <span>SIGNALS & MARKETS</span>
          <span className="bp-count">
            {p3 === "odds"
              ? predictions.length
              : p3 === "headlines"
              ? headlines.length
              : p3 === "markets"
              ? commodities.length + freight.length
              : p3 === "flights"
              ? flights.length
              : quakesNear.length}
          </span>
        </div>
        <div className="bp-tabs">
          {(["odds", "headlines", "markets", "flights", "seismic"] as const).map((t) => (
            <button
              key={t}
              className={p3 === t ? "btab active" : "btab"}
              onClick={() => setP3(t)}
            >
              {t.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="bp-list">
          {p3 === "odds" && (
            <>
              {predictions.slice(0, 10).map((m) => (
                <a
                  key={m.market_slug}
                  className="row"
                  href={m.url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className={`sev-tag ${(m.yes_price ?? 0) >= 0.5 ? "crit" : "mid"}`}>
                    {m.yes_price !== null ? `${(m.yes_price * 100).toFixed(0)}%` : "—"}
                  </span>
                  <span className="row-main">
                    <span className="row-title clamp2">{m.question}</span>
                    <span className="row-sub">
                      polymarket · $
                      {(m.volume_24h_usd ?? 0).toLocaleString(undefined, {
                        maximumFractionDigits: 0,
                      })}
                      /24h
                    </span>
                  </span>
                </a>
              ))}
              {predictions.length === 0 && <div className="empty">// no open markets</div>}
            </>
          )}

          {p3 === "headlines" && (
            <>
              <div className="inline-select">
                <select
                  className="cmd-select"
                  value={headlineRegion}
                  onChange={(e) => setHeadlineRegion(e.target.value)}
                >
                  {HEADLINE_REGIONS.map((r) => (
                    <option key={r} value={r}>
                      {r.replace(/_/g, " ").toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
              {headlines.map((h) => (
                <a
                  key={h.id}
                  className="row"
                  href={h.source_url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                >
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

          {p3 === "markets" && (
            <>
              <div className="tab-section-head">TRACKED COMMODITIES</div>
              {commodities.map((c) => (
                <div key={c.commodity_code} className="row">
                  <span className={`sev-tag ${(c.change_pct ?? 0) >= 0 ? "pos" : "neg"}`}>
                    {fmtPct(c.change_pct)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">{c.name}</span>
                    <span className="row-sub">
                      ${c.price_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })} USD
                    </span>
                  </span>
                </div>
              ))}
              <div className="tab-section-head" style={{ marginTop: 8 }}>
                GLOBAL FREIGHT INDICES
              </div>
              {freight.map((fr) => (
                <div key={fr.index_code} className="row">
                  <span className={`sev-tag ${(fr.change_pct ?? 0) >= 0 ? "high" : "pos"}`}>
                    {fmtPct(fr.change_pct)}
                  </span>
                  <span className="row-main">
                    <span className="row-title">{fr.name}</span>
                    <span className="row-sub">
                      ${fr.rate_usd.toLocaleString()} / FEU {fr.is_estimated ? "(est)" : ""}
                    </span>
                  </span>
                </div>
              ))}
            </>
          )}

          {p3 === "flights" && (
            <>
              {flights.slice(0, 14).map((fl) => (
                <div
                  key={fl.hex}
                  className="row row-clickable"
                  onClick={() => onFlyToLocation?.([fl.longitude, fl.latitude], 6)}
                >
                  <span className="sev-tag mid">{fl.aircraft_type ?? "MIL"}</span>
                  <span className="row-main">
                    <span className="row-title">
                      {fl.callsign || fl.hex} · {fl.registration || "No Reg"}
                    </span>
                    <span className="row-sub">
                      {fl.altitude_ft ? `${fl.altitude_ft.toLocaleString()} ft` : "ground"} ·{" "}
                      {fl.ground_speed_kt ? `${fl.ground_speed_kt.toFixed(0)} kt` : "—"} · sq{" "}
                      {fl.squawk || "—"}
                    </span>
                  </span>
                </div>
              ))}
              {flights.length === 0 && <div className="empty">// no military flights active</div>}
            </>
          )}

          {p3 === "seismic" && (
            <>
              {quakesNear.slice(0, 10).map((q) => (
                <div
                  key={q.external_id}
                  className="row row-clickable"
                  onClick={() => onFlyToLocation?.([q.longitude, q.latitude], 6)}
                >
                  <span className="sev-tag mid">M{q.magnitude.toFixed(1)}</span>
                  <span className="row-main">
                    <span className="row-title clamp2">{q.place ?? "—"}</span>
                    <span className="row-sub">
                      {q.near_chokepoint_code} · {q.distance_to_chokepoint_km?.toFixed(0)}km ·{" "}
                      {timeAgo(q.occurred_at)}
                    </span>
                  </span>
                </div>
              ))}
              {quakesNear.length === 0 && (
                <div className="empty">// no quakes near chokepoints</div>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
};

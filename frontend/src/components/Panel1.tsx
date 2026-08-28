import { useUIStore } from '../store';
import type { FeedItem, GovernmentAction, Protest } from '../types';
import { timeAgo } from '../utils/format';

interface Panel1Props {
  feed: FeedItem[];
  govActions: GovernmentAction[];
  protests: Protest[];
}

export function Panel1({ feed, govActions, protests }: Panel1Props) {
  const { p1, setP1 } = useUIStore();

  const bilateralFeed = feed.filter((f: FeedItem) => {
    const a1 = (f.actor1_code || "").trim().toUpperCase();
    const a2 = (f.actor2_code || "").trim().toUpperCase();
    return a1 && a2 && a1 !== a2 && a1 !== "-" && a2 !== "-" && a1 !== "—" && a2 !== "—";
  });

  const count = p1 === 'escalations' ? bilateralFeed.length : p1 === 'gov_actions' ? govActions.length : Math.min(12, protests.length);

  return (
    <section className="bp">
      <div className="bp-head">
        <span>PUBLIC & POLICY ACTIONS</span>
        <span className="bp-count">{count}</span>
      </div>
      <div className="bp-tabs">
        <button className={p1 === 'escalations' ? 'btab active' : 'btab'} onClick={() => setP1('escalations')}>
          ESCALATIONS ({bilateralFeed.length})
        </button>
        <button className={p1 === 'gov_actions' ? 'btab active' : 'btab'} onClick={() => setP1('gov_actions')}>
          GOV ACTIONS ({govActions.length})
        </button>
        <button className={p1 === 'protests' ? 'btab active' : 'btab'} onClick={() => setP1('protests')}>
          CIVIL UNREST ({Math.min(12, protests.length)})
        </button>
      </div>
      <div className="bp-list">
        {p1 === 'escalations' && (
          <>
            {bilateralFeed.length === 0 && <div className="empty">// no bilateral escalations in window</div>}
            {bilateralFeed.slice(0, 14).map((f: FeedItem) => (
              <a key={f.global_event_id} className="row" href={f.source_url ?? '#'} target="_blank" rel="noreferrer">
                <span className={`sev-tag ${f.event_severity <= -3 ? 'crit' : 'high'}`}>{f.event_severity.toFixed(1)}</span>
                <span className="row-main">
                  <span className="row-title">{f.actor1_code} → {f.actor2_code}{f.country_code ? ` · ${f.country_code}` : ''}</span>
                  <span className="row-sub">{f.num_mentions} mentions · {timeAgo(f.ingested_at ?? f.event_date)} ago</span>
                </span>
              </a>
            ))}
          </>
        )}

        {p1 === 'gov_actions' && (
          <>
            {govActions.length === 0 && <div className="empty">// no government actions recorded</div>}
            {govActions.map((g: GovernmentAction) => (
              <a key={g.rank} className="row" href={g.source_url ?? '#'} target="_blank" rel="noreferrer">
                <span className={`sev-tag ${g.action_type === 'diplomatic' ? 'pos' : g.action_type === 'security' ? 'crit' : g.action_type === 'fiscal' ? 'high' : 'mid'}`}>
                  {g.action_type ? g.action_type.toUpperCase().slice(0, 7) : 'GOV'}
                </span>
                <span className="row-main">
                  <span className="row-title clamp2">#{g.rank} · {g.headline}</span>
                  {g.llm_brief && <span className="row-sub clamp2">{g.llm_brief}</span>}
                  {g.published_at && <span className="row-sub">{timeAgo(g.published_at)} ago</span>}
                </span>
              </a>
            ))}
          </>
        )}

        {p1 === 'protests' && (
          <>
            {protests.length === 0 && <div className="empty">// no civil unrest recorded</div>}
            {protests.slice(0, 12).map((p: Protest) => (
              <a key={p.id} className="row" href={p.source_url ?? '#'} target="_blank" rel="noreferrer">
                <span className={`sev-tag ${p.event_severity >= 80 ? 'crit' : p.event_severity >= 60 ? 'high' : 'mid'}`}>
                  {p.location_name ? p.location_name.toUpperCase().slice(0, 8) : p.city ? p.city.toUpperCase().slice(0, 8) : 'UNREST'}
                </span>
                <span className="row-main">
                  <span className="row-title clamp2">{p.headline}</span>
                  {p.llm_brief && <span className="row-sub clamp2">{p.llm_brief}</span>}
                  <span className="row-sub">
                    {p.location_level ? `[${p.location_level.toUpperCase()}] ` : ''}{p.location_name && p.location_name !== p.city ? `${p.location_name}, ` : ''}{p.state ? `${p.state} · ` : ''}{p.event_date} · Sev: {p.event_severity.toFixed(0)}/100{p.validation_source ? ` · (${p.validation_source.toUpperCase()})` : ''}
                  </span>
                </span>
              </a>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
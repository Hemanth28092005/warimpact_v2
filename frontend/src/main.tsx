import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

type Commodity = { commodity_code: string; name: string; price_usd: number; change_pct: number | null };
type Freight = { index_code: string; name: string; rate_usd: number; change_pct: number | null; is_estimated: boolean };
type Quake = { external_id: string; magnitude: number; place: string | null; latitude: number; longitude: number; near_chokepoint_code: string | null; distance_to_chokepoint_km: number | null; occurred_at: string };
type Prediction = { market_slug: string; question: string; yes_price: number | null; volume_24h_usd: number | null; url: string | null };
type Protest = { id: number; headline: string; event_date: string; location_name?: string | null; location_level?: string | null; state?: string | null; country_code?: string | null; city?: string | null; action_geo_lat?: number | null; action_geo_long?: number | null; event_severity: number; llm_brief?: string | null; source_url?: string | null; validation_source?: string | null; updated_at?: string };
type FeedItem = { global_event_id: number; event_date: string; ingested_at: string | null; country_code: string | null; actor1_code: string | null; actor2_code: string | null; event_severity: number; num_mentions: number; source_url: string | null };
type CiiScore = { country_code: string; cii_score: number; confidence_interval_low?: number; confidence_interval_high?: number };
type Chokepoint = { code: string; name: string; lat: number; long: number; disruption_score: number; status: string; baseline_mbd: number; last_disruption_reason?: string | null };
type TradeRoute = { id: number; commodity_code: string; partner_country: string; primary_chokepoint: string | null; origin_lat: number; origin_long: number; dest_lat: number; dest_long: number; risk_score: number };
type AggressionPair = { country_a: string; country_b: string; aggression_score: number | null; event_count: number; data_source: string };
type CascadePair = { source_country: string; target_country: string; contagion_score: number; co_spike_count: number; source_spike_count: number };
type Headline = { id: number; region: string; rank: number; headline: string; source_url: string | null; llm_brief: string | null };
type GovernmentAction = { rank: number; headline: string; action_type: string; gdelt_event_id: number | null; source_url: string | null; published_at: string | null; llm_brief: string | null; validation_source: string | null; updated_at: string };

type Flight = {
  hex: string;
  registration: string | null;
  aircraft_type: string | null;
  callsign: string | null;
  latitude: number;
  longitude: number;
  altitude_ft: number | null;
  ground_speed_kt: number | null;
  squawk: string | null;
  observed_at: string;
};

type IntelSite = {
  category: string;
  name: string;
  country_code: string | null;
  latitude: number;
  longitude: number;
  is_estimated: boolean;
};

type IntelRoute = {
  category: string;
  name: string;
  from_name: string;
  from_lat: number;
  from_long: number;
  to_name: string;
  to_lat: number;
  to_long: number;
  is_estimated: boolean;
};

type WorldBrief = {
  brief: string;
  generated_at: string;
  signals: {
    top_cii: [string, number][];
    events_24h: number;
    hot_chokepoints: number;
  };
  model: string;
};

const REGIONS = ["usa", "europe", "middle_east", "india"] as const;
const WINDOWS_H = [1, 6, 24, 48, 168] as const;
const CASCADE_COUNTRIES = ["ISR", "UKR", "SYR", "YEM", "SDN", "PAK", "RUS", "CHN"] as const;
const HEADLINE_REGIONS = ["middle_east", "europe", "united_states", "india", "asia_pacific", "africa", "latin_america_australia"] as const;

const TV_CHANNELS = [
  { id: "aljazeera", name: "AL JAZEERA", url: "https://www.youtube-nocookie.com/embed/live_stream?channel=UCfiwzLy-8yKzIbsmZTzxDgw&autoplay=1&mute=1" },
  { id: "skynews", name: "SKY NEWS", url: "https://www.youtube-nocookie.com/embed/live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ&autoplay=1&mute=1" },
  { id: "dw", name: "DW NEWS", url: "https://www.youtube-nocookie.com/embed/live_stream?channel=UCknLrEdhRCp1aegoMqRaCZg&autoplay=1&mute=1" },
  { id: "france24", name: "FRANCE 24", url: "https://www.youtube-nocookie.com/embed/live_stream?channel=UCQfwfsi5VrQ8yKZ-UWmAEFg&autoplay=1&mute=1" },
  { id: "euronews", name: "EURONEWS", url: "https://www.youtube-nocookie.com/embed/live_stream?channel=UCSrZ3UV4jOidv8ppoVuvW9Q&autoplay=1&mute=1" },
] as const;

// Realistic Photorealistic Satellite Style with Topo-Bathymetry and Dark Tactical options
const REALISTIC_SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  name: "Realistic Satellite",
  sources: {
    "esri-satellite": {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Esri, Earthstar Geographics",
    },
  },
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#010308" },
    },
    {
      id: "satellite-base",
      type: "raster",
      source: "esri-satellite",
      paint: {
        "raster-brightness-max": 0.88,
        "raster-contrast": 0.15,
        "raster-saturation": -0.05,
      },
    },
  ],
};

const DARK_TACTICAL_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

async function api<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${Math.max(1, m)}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function utcClock(): string {
  const d = new Date();
  const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const p = (n: number) => String(n).padStart(2, "0");
  return `${days[d.getUTCDay()]}, ${p(d.getUTCDate())} ${["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"][d.getUTCMonth()]} ${d.getUTCFullYear()} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
}

function defcon(avgCii: number | null): number {
  if (avgCii === null) return 5;
  if (avgCii >= 72) return 2;
  if (avgCii >= 58) return 3;
  if (avgCii >= 42) return 4;
  return 5;
}

function greatCircle(a: [number, number], b: [number, number], n = 48): [number, number][] {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toDeg = (r: number) => (r * 180) / Math.PI;
  const lat1 = toRad(a[1]), lon1 = toRad(a[0]), lat2 = toRad(b[1]), lon2 = toRad(b[0]);
  const v1 = [Math.cos(lat1) * Math.cos(lon1), Math.cos(lat1) * Math.sin(lon1), Math.sin(lat1)];
  const v2 = [Math.cos(lat2) * Math.cos(lon2), Math.cos(lat2) * Math.sin(lon2), Math.sin(lat2)];
  const omega = Math.acos(Math.min(1, Math.max(-1, v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2])));
  const pts: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const s1 = Math.sin((1 - t) * omega) / Math.sin(omega);
    const s2 = Math.sin(t * omega) / Math.sin(omega);
    const x = s1 * v1[0] + s2 * v2[0];
    const y = s1 * v1[1] + s2 * v2[1];
    const z = s1 * v1[2] + s2 * v2[2];
    pts.push([toDeg(Math.atan2(y, x)), toDeg(Math.atan2(z, Math.sqrt(x * x + y * y)))]);
  }
  return pts;
}

function calculateBearing(start: [number, number], end: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toDeg = (r: number) => (r * 180) / Math.PI;
  const lon1 = toRad(start[0]), lat1 = toRad(start[1]);
  const lon2 = toRad(end[0]), lat2 = toRad(end[1]);
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

let popup: maplibregl.Popup | null = null;
function showPopup(map: maplibregl.Map, lngLat: maplibregl.LngLat, html: string) {
  if (popup) popup.remove();
  popup = new maplibregl.Popup({ closeButton: false, closeOnClick: true, offset: 8 })
    .setLngLat(lngLat)
    .setHTML(html)
    .addTo(map);
}

type Panel1Tab = "escalations" | "gov_actions" | "protests";
type Panel2Tab = "cii" | "chokepoints" | "aggression" | "cascade" | "routes";
type Panel3Tab = "odds" | "headlines" | "markets" | "flights" | "seismic";
type MapTheme = "satellite" | "dark";

function App(): JSX.Element {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [view3d, setView3d] = useState(true);
  const [mapTheme, setMapTheme] = useState<MapTheme>("satellite");
  const [autoRotate, setAutoRotate] = useState(false);

  const [commodities, setCommodities] = useState<Commodity[]>([]);
  const [freight, setFreight] = useState<Freight[]>([]);
  const [quakes, setQuakes] = useState<Quake[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [protests, setProtests] = useState<Protest[]>([]);
  const [govActions, setGovActions] = useState<GovernmentAction[]>([]);
  const [chokepoints, setChokepoints] = useState<Chokepoint[]>([]);
  const [routes, setRoutes] = useState<TradeRoute[]>([]);
  const [aggression, setAggression] = useState<AggressionPair[]>([]);
  const [cascade, setCascade] = useState<CascadePair[]>([]);
  const [cascadeCountry, setCascadeCountry] = useState<string>("ISR");
  const [headlines, setHeadlines] = useState<Headline[]>([]);
  const [headlineRegion, setHeadlineRegion] = useState<string>("middle_east");
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [region, setRegion] = useState<(typeof REGIONS)[number]>("middle_east");
  const [windowH, setWindowH] = useState<number>(168);
  const [ciiScores, setCiiScores] = useState<Map<string, number>>(new Map());
  const [clock, setClock] = useState(utcClock());

  // Geospatial layers state
  const [flights, setFlights] = useState<Flight[]>([]);
  const [intelSites, setIntelSites] = useState<IntelSite[]>([]);
  const [intelRoutes, setIntelRoutes] = useState<IntelRoute[]>([]);
  const [boundariesData, setBoundariesData] = useState<{ iso_a3: string; geojson: object }[]>([]);

  const [layers, setLayers] = useState({
    cii: true,
    routes: true,
    quakes: true,
    chokes: true,
    protests: false,
    flights: true,
    bases: true,
    nuclear: true,
    spaceports: false,
    cables: true,
  });

  const [loaded, setLoaded] = useState({
    cii: false,
    quakes: false,
    chokes: false,
    protests: false,
    routes: false,
    flights: false,
    intel: false,
  });

  const [p1, setP1] = useState<Panel1Tab>("escalations");
  const [p2, setP2] = useState<Panel2Tab>("cii");
  const [p3, setP3] = useState<Panel3Tab>("odds");

  // AI Brief overlay state
  const [showBrief, setShowBrief] = useState(false);
  const [briefData, setBriefData] = useState<WorldBrief | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [briefError, setBriefError] = useState<string | null>(null);

  // Live TV state
  const [showTv, setShowTv] = useState(false);
  const [tvChannel, setTvChannel] = useState<string>("aljazeera");
  const [tvMinimized, setTvMinimized] = useState(false);

  useEffect(() => {
    const iv = setInterval(() => setClock(utcClock()), 1000);
    return () => clearInterval(iv);
  }, []);

  const loadBrief = async (bypass = false) => {
    setBriefLoading(true);
    setBriefError(null);
    try {
      const data = await api<WorldBrief>(`/api/v1/brief/world${bypass ? "?bypass_cache=true" : ""}`);
      setBriefData(data);
    } catch (err: unknown) {
      setBriefError(err instanceof Error ? err.message : "Failed to load situation brief");
    } finally {
      setBriefLoading(false);
    }
  };

  useEffect(() => {
    if (showBrief && !briefData && !briefLoading) {
      loadBrief(false);
    }
  }, [showBrief]);

  useEffect(() => {
    let cancelled = false;
    api<{ items: FeedItem[] }>(`/api/v1/live-feed/${region}?window_hours=${windowH}`)
      .then((d) => { if (!cancelled) setFeed(d.items ?? []); })
      .catch(() => { if (!cancelled) setFeed([]); });
    return () => { cancelled = true; };
  }, [region, windowH]);

  useEffect(() => {
    let cancelled = false;
    api<{ pairs: CascadePair[] }>(`/api/v1/cascade/${cascadeCountry}?window_days=7`)
      .then((d) => { if (!cancelled) setCascade(d.pairs ?? []); })
      .catch(() => { if (!cancelled) setCascade([]); });
    return () => { cancelled = true; };
  }, [cascadeCountry]);

  useEffect(() => {
    let cancelled = false;
    api<Headline[]>(`/api/v1/dashboard/regional-headlines?region=${headlineRegion}`)
      .then((d) => { if (!cancelled) setHeadlines(d ?? []); })
      .catch(() => { if (!cancelled) setHeadlines([]); });
    return () => { cancelled = true; };
  }, [headlineRegion]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const results = await Promise.allSettled([
        api<Commodity[]>("/api/v1/markets/commodities"),
        api<Freight[]>("/api/v1/markets/shipping"),
        api<Quake[]>("/api/v1/events/earthquakes?hours=168&min_magnitude=4&limit=150"),
        api<Prediction[]>("/api/v1/events/prediction-markets?limit=20"),
        api<Protest[]>("/api/v1/dashboard/protests?limit=100"),
        api<GovernmentAction[]>("/api/v1/dashboard/government-actions"),
        api<Chokepoint[]>("/api/v1/dashboard/chokepoints"),
        api<TradeRoute[]>("/api/v1/dashboard/trade-routes"),
        api<{ pairs: AggressionPair[] }>("/api/v1/aggression/matrix"),
        api<Flight[]>("/api/v1/events/flights?limit=500"),
        api<{ sites: IntelSite[]; routes: IntelRoute[] }>("/api/v1/events/intel"),
      ]);
      if (cancelled) return;
      if (results[0].status === "fulfilled") setCommodities(results[0].value);
      if (results[1].status === "fulfilled") setFreight(results[1].value);
      if (results[2].status === "fulfilled") { setQuakes(results[2].value); setLoaded((l) => ({ ...l, quakes: true })); }
      if (results[3].status === "fulfilled") setPredictions(results[3].value);
      if (results[4].status === "fulfilled") { setProtests(results[4].value); setLoaded((l) => ({ ...l, protests: true })); }
      if (results[5].status === "fulfilled") setGovActions(results[5].value);
      if (results[6].status === "fulfilled") { setChokepoints(results[6].value); setLoaded((l) => ({ ...l, chokes: true })); }
      if (results[7].status === "fulfilled") { setRoutes(results[7].value); setLoaded((l) => ({ ...l, routes: true })); }
      if (results[8].status === "fulfilled") setAggression(results[8].value.pairs ?? []);
      if (results[9].status === "fulfilled") { setFlights(results[9].value); setLoaded((l) => ({ ...l, flights: true })); }
      if (results[10].status === "fulfilled") {
        setIntelSites(results[10].value.sites ?? []);
        setIntelRoutes(results[10].value.routes ?? []);
        setLoaded((l) => ({ ...l, intel: true }));
      }
    };
    load();
    const iv = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  // Map Initialization & Realistic Satellite Setup
  useEffect(() => {
    const styleObj = mapTheme === "satellite" ? REALISTIC_SATELLITE_STYLE : DARK_TACTICAL_STYLE;
    const map = new maplibregl.Map({
      container: "globe",
      style: styleObj,
      center: [42, 26],
      zoom: view3d ? 1.6 : 2,
      attributionControl: false,
      maxPitch: 85,
    });
    mapRef.current = map;

    map.on("style.load", () => {
      map.setProjection({ type: view3d ? "globe" : "mercator" });
    });

    (async () => {
      try {
        const [boundaries, scores] = await Promise.all([
          api<{ iso_a3: string; geojson: object }[]>("/api/v1/dashboard/boundaries"),
          api<CiiScore[]>("/api/v1/cii/latest"),
        ]);
        setBoundariesData(boundaries);
        const scoreMap = new Map<string, number>(scores.map((s) => [s.country_code, s.cii_score]));
        setCiiScores(scoreMap);

        const features = boundaries
          .filter((b) => b.geojson)
          .map((b) => {
            const gj = b.geojson as { properties?: Record<string, unknown> };
            const cii = scoreMap.get(b.iso_a3);
            return { ...gj, properties: { ...(gj.properties ?? {}), iso_a3: b.iso_a3, __cii: cii === undefined ? -1 : cii } };
          });

        await new Promise<void>((r) => (map.loaded() ? r() : map.once("load", () => r())));

        if (!map.getSource("countries")) {
          map.addSource("countries", { type: "geojson", data: { type: "FeatureCollection", features } as never });
          map.addLayer({
            id: "cii-fill",
            type: "fill",
            source: "countries",
            paint: {
              "fill-color": [
                "case",
                ["<=", ["get", "__cii"], 0],
                "transparent",
                ["interpolate", ["linear"], ["get", "__cii"], 10, "rgba(58,21,32,0.3)", 30, "rgba(138,26,26,0.45)", 50, "rgba(194,37,37,0.55)", 70, "rgba(255,64,48,0.65)", 90, "rgba(255,122,92,0.75)"],
              ] as never,
              "fill-opacity": 0.8,
            },
          });
          map.addLayer({
            id: "cii-line",
            type: "line",
            source: "countries",
            paint: {
              "line-color": mapTheme === "satellite" ? "rgba(56, 189, 248, 0.45)" : "#3a3f52",
              "line-width": 0.75,
            },
          });
          setLoaded((l) => ({ ...l, cii: true }));

          map.on("mousemove", "cii-fill", (e) => {
            const f = e.features?.[0];
            if (!f) return;
            map.getCanvas().style.cursor = "crosshair";
            const code = f.properties?.iso_a3 as string;
            const score = scoreMap.get(code);
            showPopup(map, e.lngLat, `<div class="wm-pop"><span class="wm-pop-code">${code}</span><br/>CII <b>${score !== undefined ? score.toFixed(1) : "—"}</b>/100</div>`);
          });
          map.on("mouseleave", "cii-fill", () => { map.getCanvas().style.cursor = ""; if (popup) popup.remove(); });
        }
      } catch (err) {
        console.error("boundary load failed", err);
      }
    })();

    return () => map.remove();
  }, [mapTheme]);

  // Handle Projection changes (Globe vs Mercator)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyProjection = () => map.setProjection({ type: view3d ? "globe" : "mercator" });
    if (map.isStyleLoaded()) {
      applyProjection();
    } else {
      map.once("style.load", applyProjection);
    }
  }, [view3d]);

  // Auto-rotation when in 3D mode
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !view3d || !autoRotate) return;
    let animId: number;
    let isInteracting = false;

    const onMouseDown = () => { isInteracting = true; };
    const onMouseUp = () => { isInteracting = false; };
    map.on("mousedown", onMouseDown);
    map.on("mouseup", onMouseUp);
    map.on("touchstart", onMouseDown);
    map.on("touchend", onMouseUp);

    const rotate = () => {
      if (!isInteracting && mapRef.current && view3d && autoRotate) {
        const center = map.getCenter();
        center.lng = (center.lng + 0.08) % 360;
        map.setCenter(center);
      }
      animId = requestAnimationFrame(rotate);
    };
    animId = requestAnimationFrame(rotate);

    return () => {
      cancelAnimationFrame(animId);
      map.off("mousedown", onMouseDown);
      map.off("mouseup", onMouseUp);
      map.off("touchstart", onMouseDown);
      map.off("touchend", onMouseUp);
    };
  }, [view3d, autoRotate]);

  // Render & Update all Dynamic Layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      // 1. Quakes
      const quakeData = {
        type: "FeatureCollection" as const,
        features: quakes.map((q) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [q.longitude, q.latitude] },
          properties: { mag: q.magnitude, place: q.place ?? "", id: q.external_id },
        })),
      };
      if (!map.getSource("quakes") && loaded.quakes) {
        map.addSource("quakes", { type: "geojson", data: quakeData as never });
        map.addLayer({
          id: "quake-circles",
          type: "circle",
          source: "quakes",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["get", "mag"], 4, 3.5, 6, 9, 8, 18],
            "circle-color": "#ffb020",
            "circle-stroke-color": "#ff7a00",
            "circle-stroke-width": 1.2,
            "circle-opacity": 0.7,
          },
        });
        map.on("click", "quake-circles", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          showPopup(map, e.lngLat, `<div class="wm-pop">M<b>${f.properties?.mag}</b><br/><span class="wm-pop-dim">${f.properties?.place}</span></div>`);
        });
      } else if (map.getSource("quakes")) {
        (map.getSource("quakes") as maplibregl.GeoJSONSource).setData(quakeData as never);
      }

      // 2. Protests
      if (!map.getSource("protest-points") && loaded.protests) {
        const pts = protests.filter((p) => p.action_geo_lat != null && p.action_geo_long != null);
        const data = {
          type: "FeatureCollection" as const,
          features: pts.map((p) => ({
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [Number(p.action_geo_long), Number(p.action_geo_lat)] },
            properties: { sev: Number(p.event_severity), headline: p.headline, loc: p.location_name || p.city || "" },
          })),
        };
        map.addSource("protest-points", { type: "geojson", data: data as never });
        map.addLayer({
          id: "protest-circles",
          type: "circle",
          source: "protest-points",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["get", "sev"], 0, 3.5, 50, 7, 100, 11],
            "circle-color": "#ffd23c",
            "circle-stroke-color": "#000000aa",
            "circle-stroke-width": 1,
            "circle-opacity": 0.85,
          },
        });
        map.on("click", "protest-circles", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          showPopup(map, e.lngLat, `<div class="wm-pop"><span class="wm-pop-dim">${f.properties?.loc}</span><br/>${f.properties?.headline}</div>`);
        });
      }

      // 3. Trade routes
      if (!map.getSource("trade-routes") && loaded.routes && routes.length > 0) {
        const features = routes.map((r) => ({
          type: "Feature" as const,
          geometry: {
            type: "LineString" as const,
            coordinates: greatCircle([r.origin_long, r.origin_lat], [r.dest_long, r.dest_lat]),
          },
          properties: {
            risk: r.risk_score,
            commodity: r.commodity_code,
            partner: r.partner_country,
            choke: r.primary_chokepoint ?? "direct",
            color: r.risk_score >= 80 ? "#ef4444" : r.risk_score >= 60 ? "#f97316" : r.risk_score >= 35 ? "#eab308" : "#22d3ee",
          },
        }));
        // Base subtle background track
        map.addSource("trade-routes", { type: "geojson", data: { type: "FeatureCollection", features } as never });
        map.addLayer({
          id: "route-lines-base",
          type: "line",
          source: "trade-routes",
          paint: {
            "line-color": [
              "interpolate", ["linear"], ["get", "risk"],
              0, "#2fd67b", 40, "#eab308", 65, "#f97316", 85, "#ef4444",
            ] as never,
            "line-width": 1.2,
            "line-opacity": 0.22,
          },
          layout: { "line-cap": "round" },
        });

        // Dynamic moving active line segments (oscillating back & forth with staggered timings)
        if (!map.getSource("trade-routes-active")) {
          map.addSource("trade-routes-active", {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] } as never,
          });
          map.addLayer({
            id: "route-lines-glow",
            type: "line",
            source: "trade-routes-active",
            paint: {
              "line-color": ["get", "color"],
              "line-width": ["interpolate", ["linear"], ["zoom"], 1, 4.0, 4, 6.0, 8, 9.0],
              "line-opacity": 0.45,
              "line-blur": 2.2,
            },
            layout: { "line-cap": "round", "line-join": "round" },
          });
          map.addLayer({
            id: "route-lines-active",
            type: "line",
            source: "trade-routes-active",
            paint: {
              "line-color": ["get", "color"],
              "line-width": ["interpolate", ["linear"], ["zoom"], 1, 2.2, 4, 3.2, 8, 4.5],
              "line-opacity": 0.95,
            },
            layout: { "line-cap": "round", "line-join": "round" },
          });
        }

        const handleRouteClick = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
          const f = e.features?.[0];
          if (!f) return;
          showPopup(map, e.lngLat, `<div class="wm-pop"><span class="wm-pop-code">${f.properties?.commodity}</span> → ${f.properties?.partner}<br/>risk <b>${Number(f.properties?.risk).toFixed(1)}</b>/100<br/><span class="wm-pop-dim">via ${f.properties?.choke ?? "direct corridor"}</span></div>`);
        };
        map.on("click", "route-lines-base", handleRouteClick);
        map.on("click", "route-lines-active", handleRouteClick);
      }

      // 4. Military Flights
      const flightData = {
        type: "FeatureCollection" as const,
        features: flights.map((fl) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [fl.longitude, fl.latitude] },
          properties: {
            hex: fl.hex,
            callsign: fl.callsign ?? fl.hex,
            type: fl.aircraft_type ?? "MIL",
            alt: fl.altitude_ft,
            spd: fl.ground_speed_kt,
            squawk: fl.squawk,
            reg: fl.registration,
          },
        })),
      };
      if (!map.getSource("military-flights") && loaded.flights && flights.length > 0) {
        map.addSource("military-flights", { type: "geojson", data: flightData as never });
        map.addLayer({
          id: "flight-circles",
          type: "circle",
          source: "military-flights",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2.5, 4, 4, 8, 7],
            "circle-color": "#00e5ff",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 0.8,
            "circle-opacity": 0.95,
          },
        });
        map.on("click", "flight-circles", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          const altStr = f.properties?.alt ? `${Number(f.properties?.alt).toLocaleString()} ft` : "—";
          const spdStr = f.properties?.spd ? `${Number(f.properties?.spd).toFixed(0)} kt` : "—";
          showPopup(map, e.lngLat, `
            <div class="wm-pop">
              <span class="wm-pop-code">${f.properties?.callsign}</span> · <span class="wm-pop-dim">${f.properties?.type}</span><br/>
              Alt: <b>${altStr}</b> · Spd: <b>${spdStr}</b><br/>
              <span class="wm-pop-dim">Squawk: ${f.properties?.squawk ?? "—"} · Reg: ${f.properties?.reg ?? "—"}</span>
            </div>
          `);
        });
      } else if (map.getSource("military-flights")) {
        (map.getSource("military-flights") as maplibregl.GeoJSONSource).setData(flightData as never);
      }

      // 5. Intel Sites (Bases, Nuclear, Spaceports)
      const siteData = {
        type: "FeatureCollection" as const,
        features: intelSites.map((s) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [s.longitude, s.latitude] },
          properties: {
            cat: s.category,
            name: s.name,
            cc: s.country_code ?? "",
            est: s.is_estimated,
          },
        })),
      };
      if (!map.getSource("intel-sites") && loaded.intel && intelSites.length > 0) {
        map.addSource("intel-sites", { type: "geojson", data: siteData as never });

        // Military bases
        map.addLayer({
          id: "intel-bases-layer",
          type: "circle",
          source: "intel-sites",
          filter: ["==", ["get", "cat"], "military_base"],
          paint: {
            "circle-radius": 5,
            "circle-color": "#c084fc",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.2,
            "circle-opacity": 0.95,
          },
        });

        // Nuclear sites
        map.addLayer({
          id: "intel-nuclear-layer",
          type: "circle",
          source: "intel-sites",
          filter: ["==", ["get", "cat"], "nuclear_site"],
          paint: {
            "circle-radius": 5.5,
            "circle-color": "#ef4444",
            "circle-stroke-color": "#ffd23c",
            "circle-stroke-width": 1.4,
            "circle-opacity": 1.0,
          },
        });

        // Spaceports
        map.addLayer({
          id: "intel-spaceports-layer",
          type: "circle",
          source: "intel-sites",
          filter: ["==", ["get", "cat"], "spaceport"],
          paint: {
            "circle-radius": 5,
            "circle-color": "#38bdf8",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.2,
            "circle-opacity": 0.95,
          },
        });

        const handleSiteClick = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
          const f = e.features?.[0];
          if (!f) return;
          const catLabel = String(f.properties?.cat ?? "").replace("_", " ").toUpperCase();
          showPopup(map, e.lngLat, `
            <div class="wm-pop">
              <span class="wm-pop-code">${catLabel}</span><br/>
              <b>${f.properties?.name}</b> (${f.properties?.cc || "—"})<br/>
              <span class="wm-pop-dim">Strategic intelligence facility</span>
            </div>
          `);
        };
        map.on("click", "intel-bases-layer", handleSiteClick);
        map.on("click", "intel-nuclear-layer", handleSiteClick);
        map.on("click", "intel-spaceports-layer", handleSiteClick);
      } else if (map.getSource("intel-sites")) {
        (map.getSource("intel-sites") as maplibregl.GeoJSONSource).setData(siteData as never);
      }

      // 6. Intel Routes (Cables & Pipelines)
      const intelRouteFeatures = intelRoutes.map((r) => ({
        type: "Feature" as const,
        geometry: {
          type: "LineString" as const,
          coordinates: greatCircle([r.from_long, r.from_lat], [r.to_long, r.to_lat]),
        },
        properties: {
          cat: r.category,
          name: r.name,
          fn: r.from_name,
          tn: r.to_name,
        },
      }));
      const intelRouteData = {
        type: "FeatureCollection" as const,
        features: intelRouteFeatures,
      };
      if (!map.getSource("intel-routes") && loaded.intel && intelRoutes.length > 0) {
        map.addSource("intel-routes", { type: "geojson", data: intelRouteData as never });
        map.addLayer({
          id: "intel-routes-lines",
          type: "line",
          source: "intel-routes",
          paint: {
            "line-color": [
              "match",
              ["get", "cat"],
              "undersea_cable", "#06b6d4",
              "pipeline", "#f59e0b",
              "#94a3b8",
            ] as never,
            "line-width": 1.5,
            "line-dasharray": [3, 2],
            "line-opacity": 0.75,
          },
        });
        map.on("click", "intel-routes-lines", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          const catLabel = String(f.properties?.cat ?? "").replace("_", " ").toUpperCase();
          showPopup(map, e.lngLat, `
            <div class="wm-pop">
              <span class="wm-pop-code">${catLabel}</span><br/>
              <b>${f.properties?.name}</b><br/>
              <span class="wm-pop-dim">${f.properties?.fn} ⇄ ${f.properties?.tn}</span>
            </div>
          `);
        });
      } else if (map.getSource("intel-routes")) {
        (map.getSource("intel-routes") as maplibregl.GeoJSONSource).setData(intelRouteData as never);
      }

      // Visibility toggles
      const vis = (name: string, on: boolean) => {
        if (map.getLayer(name)) map.setLayoutProperty(name, "visibility", on ? "visible" : "none");
      };
      vis("cii-fill", layers.cii);
      vis("cii-line", layers.cii);
      vis("quake-circles", layers.quakes);
      vis("protest-circles", layers.protests);
      vis("route-lines-base", layers.routes);
      vis("route-lines-glow", layers.routes);
      vis("route-lines-active", layers.routes);
      vis("flight-circles", layers.flights);
      vis("intel-bases-layer", layers.bases);
      vis("intel-nuclear-layer", layers.nuclear);
      vis("intel-spaceports-layer", layers.spaceports);
      vis("intel-routes-lines", layers.cables);

      document.querySelectorAll(".cp-marker").forEach((el) => {
        (el as HTMLElement).style.display = layers.chokes ? "" : "none";
      });
    };
    apply();
  }, [layers, quakes, protests, routes, flights, intelSites, intelRoutes, loaded, mapTheme]);

  // Moving Commodity Transport Lines Animation (Gliding back-and-forth at staggered intervals)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded.routes || routes.length === 0 || !layers.routes) return;

    // Precompute geodesic paths and staggered oscillation parameters
    const animatedTracks = routes.map((r, idx) => {
      const path = greatCircle([r.origin_long, r.origin_lat], [r.dest_long, r.dest_lat], 50);
      const color = r.risk_score >= 80 ? "#ef4444" : r.risk_score >= 60 ? "#f97316" : r.risk_score >= 35 ? "#eab308" : "#22d3ee";
      // Stagger durations between 4200ms and 9500ms based on distance and route index
      const durationMs = 4200 + ((idx * 683) % 5500);
      // Stagger phase offset so they move back and forth at completely different times
      const phaseOffset = (idx * 1337) % 9000;
      return {
        id: r.id,
        commodity: r.commodity_code,
        partner: r.partner_country,
        risk: r.risk_score,
        color,
        path,
        durationMs,
        phaseOffset,
      };
    });

    let animId: number;
    let lastRenderTime = 0;

    const animateLines = (now: number) => {
      // Smooth ~40-60 FPS rendering
      if (now - lastRenderTime >= 24) {
        lastRenderTime = now;
        const source = map.getSource("trade-routes-active") as maplibregl.GeoJSONSource | undefined;
        if (source && map.getLayer("route-lines-active")) {
          const features: GeoJSON.Feature[] = [];
          for (const track of animatedTracks) {
            const N = track.path.length;
            if (N < 4) continue;

            // Smooth back-and-forth sinusoidal oscillation [0.0, 1.0]
            const angle = (2 * Math.PI * (now + track.phaseOffset)) / track.durationMs;
            const progress = 0.5 * (1 - Math.cos(angle));

            // Dynamic active line segment length (approx 30% to 40% of arc)
            const segLen = Math.max(6, Math.round(N * 0.35));
            const maxStart = N - segLen;
            const startIdx = Math.round(progress * maxStart);
            const endIdx = Math.min(N, startIdx + segLen);

            const segmentCoords = track.path.slice(startIdx, endIdx);
            if (segmentCoords.length >= 2) {
              features.push({
                type: "Feature",
                geometry: {
                  type: "LineString",
                  coordinates: segmentCoords,
                },
                properties: {
                  commodity: track.commodity,
                  partner: track.partner,
                  risk: track.risk,
                  color: track.color,
                },
              });
            }
          }
          source.setData({ type: "FeatureCollection", features } as never);
        }
      }
      animId = requestAnimationFrame(animateLines);
    };

    animId = requestAnimationFrame(animateLines);
    return () => {
      cancelAnimationFrame(animId);
    };
  }, [routes, loaded.routes, layers.routes]);

  // Chokepoints 3D Markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded.chokes || chokepoints.length === 0) return;
    if ((map as unknown as { _chokesAdded?: boolean })._chokesAdded) return;
    (map as unknown as { _chokesAdded?: boolean })._chokesAdded = true;
    chokepoints.forEach((cp) => {
      const el = document.createElement("div");
      el.className = `cp-marker cp-${cp.status}`;
      el.title = `${cp.name} — disruption ${cp.disruption_score.toFixed(0)} (${cp.status})`;
      new maplibregl.Marker({ element: el }).setLngLat([cp.long, cp.lat]).addTo(map);
    });
  }, [chokepoints, loaded.chokes]);

  const scoresArr = Array.from(ciiScores.entries()).sort((a, b) => b[1] - a[1]);
  const avgCii = scoresArr.length ? scoresArr.reduce((a, [, v]) => a + v, 0) / scoresArr.length : null;
  const dc = defcon(avgCii);
  const quakesNear = quakes.filter((q) => q.near_chokepoint_code);
  const topAggression = aggression
    .filter((p) => p.aggression_score !== null && p.data_source === "gdelt_derived")
    .sort((a, b) => (b.aggression_score ?? 0) - (a.aggression_score ?? 0))
    .slice(0, 14);
  const topRoutes = [...routes].sort((a, b) => b.risk_score - a.risk_score);

  const toggleLayer = (k: keyof typeof layers) => setLayers((s) => ({ ...s, [k]: !s[k] }));

  return (
    <div className="app">
      <header className="cmdbar">
        <div className="cmd-left">
          <span className="cmd-globe">◍</span>
          <span className="cmd-word">WAR</span>
          <span className="cmd-sep">·</span>
          <span className="cmd-word cmd-accent">MONITOR</span>
          <span className="cmd-ver">v0.4.0</span>
        </div>
        <div className="cmd-right">
          <button className={`cmd-btn brief-btn ${showBrief ? "active" : ""}`} onClick={() => setShowBrief(true)}>
            <span className="brief-spark">✦</span> AI BRIEF
          </button>
          <button className={`cmd-btn tv-btn ${showTv ? "active" : ""}`} onClick={() => setShowTv(!showTv)}>
            <span className="tv-icon">📺</span> LIVE TV
          </button>
          <span className="live-ind"><i />LIVE</span>
          <select className="cmd-select" value={region} onChange={(e) => setRegion(e.target.value as typeof region)}>
            {REGIONS.map((r) => (
              <option key={r} value={r}>{r.replace("_", " ").toUpperCase()}</option>
            ))}
          </select>
          <span className={`defcon-badge dc-${dc}`}>⚠ DEFCON {dc}</span>
          <span className="cmd-clock">{clock}</span>
        </div>
      </header>

      <div className="sitbar">
        <span>GLOBAL SITUATION</span>
        <span className="sit-center">
          {feed.length} ESCALATIONS · {govActions.length} GOV POLICIES · {flights.length} MIL AIRBORNE · {chokepoints.filter((c) => c.status !== "green").length} CHOKE ALERTS
        </span>
        <span className="sit-right">
          {commodities.slice(0, 3).map((c) => (
            <span key={c.commodity_code} className="sit-tick">
              {c.name.split(" ")[0].toUpperCase()}{" "}
              <b className={(c.change_pct ?? 0) >= 0 ? "up" : "down"}>{fmtPct(c.change_pct)}</b>
            </span>
          ))}
          <span className="view-toggle">
            <button
              className={mapTheme === "satellite" ? "vt active" : "vt"}
              onClick={() => setMapTheme("satellite")}
              title="Photorealistic Satellite & Bathymetry Earth"
            >
              SAT
            </button>
            <button
              className={mapTheme === "dark" ? "vt active" : "vt"}
              onClick={() => setMapTheme("dark")}
              title="Dark Cyber Tactical Matrix"
            >
              DARK
            </button>
          </span>
          <span className="view-toggle">
            <button className={!view3d ? "vt active" : "vt"} onClick={() => setView3d(false)}>2D</button>
            <button className={view3d ? "vt active" : "vt"} onClick={() => setView3d(true)}>3D</button>
          </span>
          <button
            className={`orbit-btn ${autoRotate ? "active" : ""}`}
            onClick={() => setAutoRotate(!autoRotate)}
            title="Auto-rotate Globe Orbit"
          >
            ↻ ORBIT
          </button>
        </span>
      </div>

      <div className="map-zone">
        <div id="globe" />
        <div className="globe-atmosphere-glow" />

        <div className="map-overlays">
          <div className="win-chips">
            {WINDOWS_H.map((h) => (
              <button key={h} className={windowH === h ? "chip active" : "chip"} onClick={() => setWindowH(h)}>
                {h === 168 ? "7d" : `${h}h`}
              </button>
            ))}
          </div>

          <div className="layers-panel">
            <div className="layers-head">
              <span>INTEL LAYERS</span>
              <span className="layers-q">10</span>
            </div>
            <label className="layer-row">
              <input type="checkbox" checked={layers.cii} onChange={() => toggleLayer("cii")} />
              <span className="checkmark" />
              CONFLICT (CII)
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.flights} onChange={() => toggleLayer("flights")} />
              <span className="checkmark" />
              MILITARY FLIGHTS ({flights.length})
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.bases} onChange={() => toggleLayer("bases")} />
              <span className="checkmark" />
              MILITARY BASES
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.nuclear} onChange={() => toggleLayer("nuclear")} />
              <span className="checkmark" />
              NUCLEAR SITES
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.spaceports} onChange={() => toggleLayer("spaceports")} />
              <span className="checkmark" />
              SPACEPORTS
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.cables} onChange={() => toggleLayer("cables")} />
              <span className="checkmark" />
              CABLES & PIPES
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.routes} onChange={() => toggleLayer("routes")} />
              <span className="checkmark" />
              TRADE ROUTES
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.quakes} onChange={() => toggleLayer("quakes")} />
              <span className="checkmark" />
              SEISMIC EVENTS
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.chokes} onChange={() => toggleLayer("chokes")} />
              <span className="checkmark" />
              CHOKEPOINTS
            </label>
            <label className="layer-row">
              <input type="checkbox" checked={layers.protests} onChange={() => toggleLayer("protests")} />
              <span className="checkmark" />
              CIVIL UNREST
            </label>
            <div className="layers-src">@ ESRI SATELLITE · ADSB.LOL · GDELT · USGS</div>
          </div>

          <div className="legend-bar">
            <span className="lg-title">LEGEND</span>
            <span><i className="dot d-high" /> Alert</span>
            <span><i className="dot d-flight" /> Mil Flight</span>
            <span><i className="dot d-base" /> Base</span>
            <span><i className="dot d-nuc" /> Nuclear</span>
            <span><i className="dot d-space" /> Spaceport</span>
            <span><i className="dot d-quake" /> Quake M4+</span>
            <span><i className="sq sq-red" /> Chokepoint</span>
            <span><i className="line lg-route" /> Trade Route</span>
            <span><i className="line lg-cable" /> Cable</span>
          </div>
        </div>

        {/* Live TV Floating Panel */}
        {showTv && (
          <div className={`tv-panel ${tvMinimized ? "minimized" : ""}`}>
            <div className="tv-header">
              <div className="tv-title">
                <span className="tv-rec-dot" />
                <span>LIVE NEWS BROADCAST</span>
              </div>
              <div className="tv-controls">
                <button className="tv-ctrl-btn" onClick={() => setTvMinimized(!tvMinimized)}>
                  {tvMinimized ? "▢" : "—"}
                </button>
                <button className="tv-ctrl-btn" onClick={() => setShowTv(false)}>✕</button>
              </div>
            </div>

            {!tvMinimized && (
              <>
                <div className="tv-channels">
                  {TV_CHANNELS.map((ch) => (
                    <button
                      key={ch.id}
                      className={`tv-chan-btn ${tvChannel === ch.id ? "active" : ""}`}
                      onClick={() => setTvChannel(ch.id)}
                    >
                      {ch.name}
                    </button>
                  ))}
                </div>
                <div className="tv-body">
                  {TV_CHANNELS.find((ch) => ch.id === tvChannel) && (
                    <iframe
                      className="tv-iframe"
                      src={TV_CHANNELS.find((ch) => ch.id === tvChannel)!.url}
                      title="Live News Stream"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                    />
                  )}
                </div>
                <div className="tv-footer">
                  <span>UNMUTE IN PLAYER FOR AUDIO · LOW-LATENCY EMBED</span>
                </div>
              </>
            )}
          </div>
        )}

        {/* AI Situation Brief Modal Overlay */}
        {showBrief && (
          <div className="brief-modal-overlay" onClick={() => setShowBrief(false)}>
            <div className="brief-modal" onClick={(e) => e.stopPropagation()}>
              <div className="brief-header">
                <div className="brief-title-block">
                  <span className="brief-badge">AI SYNTHESIS</span>
                  <span className="brief-title">GLOBAL SITUATION BRIEF</span>
                </div>
                <div className="brief-actions">
                  <button className="brief-btn-refresh" onClick={() => loadBrief(true)} disabled={briefLoading}>
                    {briefLoading ? "ANALYZING..." : "⟳ REFRESH BRIEF"}
                  </button>
                  <button className="brief-btn-close" onClick={() => setShowBrief(false)}>✕</button>
                </div>
              </div>

              <div className="brief-content">
                {briefLoading && (
                  <div className="brief-loading">
                    <span className="spinner" />
                    <span>SYNTHESIZING CROSS-DOMAIN GEOPOLITICAL SIGNALS VIA GROQ LLM...</span>
                  </div>
                )}

                {briefError && !briefLoading && (
                  <div className="brief-err">
                    <b>Failed to generate situation brief:</b> {briefError}
                  </div>
                )}

                {briefData && !briefLoading && (
                  <>
                    <div className="brief-quote-box">
                      <div className="brief-quote-bar" />
                      <div className="brief-quote-text">{briefData.brief}</div>
                    </div>

                    <div className="brief-signals-heading">TELEMETRY INPUTS & CORROBORATING SIGNALS</div>

                    <div className="brief-signals-grid">
                      <div className="signal-card">
                        <span className="sig-label">TOP INSTABILITY (CII)</span>
                        <div className="sig-tags">
                          {briefData.signals.top_cii.map(([code, score]) => (
                            <span key={code} className="sig-tag crit">
                              {code}: {score.toFixed(0)}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="signal-card">
                        <span className="sig-label">ELEVATED CHOKEPOINTS</span>
                        <span className="sig-value">{briefData.signals.hot_chokepoints} Monitored Corridors</span>
                      </div>

                      <div className="signal-card">
                        <span className="sig-label">24H GDELT EVENT VOLUME</span>
                        <span className="sig-value">{briefData.signals.events_24h.toLocaleString()} Events Ingested</span>
                      </div>

                      <div className="signal-card">
                        <span className="sig-label">AIRBORNE MILITARY FLEET</span>
                        <span className="sig-value">{flights.length} Active Tracks</span>
                      </div>
                    </div>

                    <div className="brief-footer-info">
                      <span>Model: <b>{briefData.model}</b></span>
                      <span>Generated at: <b>{briefData.generated_at}</b></span>
                      <button
                        className="copy-btn"
                        onClick={() => {
                          navigator.clipboard.writeText(briefData.brief);
                          alert("Situation brief copied to clipboard.");
                        }}
                      >
                        COPY TEXT
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bottom-row">
        {/* Panel 1: Live Escalations, Government Actions & Civil Unrest */}
        <section className="bp">
          <div className="bp-head">
            <span>PUBLIC & POLICY ACTIONS</span>
            <span className="bp-count">
              {p1 === "escalations" ? feed.length : p1 === "gov_actions" ? govActions.length : Math.min(12, protests.length)}
            </span>
          </div>
          <div className="bp-tabs">
            <button className={p1 === "escalations" ? "btab active" : "btab"} onClick={() => setP1("escalations")}>
              ESCALATIONS
            </button>
            <button className={p1 === "gov_actions" ? "btab active" : "btab"} onClick={() => setP1("gov_actions")}>
              GOV ACTIONS ({govActions.length})
            </button>
            <button className={p1 === "protests" ? "btab active" : "btab"} onClick={() => setP1("protests")}>
              CIVIL UNREST ({Math.min(12, protests.length)})
            </button>
          </div>
          <div className="bp-list">
            {p1 === "escalations" && (
              <>
                {feed.length === 0 && <div className="empty">// no escalations in window</div>}
                {feed.slice(0, 14).map((f) => (
                  <a key={f.global_event_id} className="row" href={f.source_url ?? "#"} target="_blank" rel="noreferrer">
                    <span className={`sev-tag ${f.event_severity <= -3 ? "crit" : "high"}`}>{f.event_severity.toFixed(1)}</span>
                    <span className="row-main">
                      <span className="row-title">{f.actor1_code ?? "—"} → {f.actor2_code ?? "—"} · {f.country_code ?? "—"}</span>
                      <span className="row-sub">{f.num_mentions} mentions · {timeAgo(f.ingested_at ?? f.event_date)} ago</span>
                    </span>
                  </a>
                ))}
              </>
            )}

            {p1 === "gov_actions" && (
              <>
                {govActions.length === 0 && <div className="empty">// no government actions recorded</div>}
                {govActions.map((g) => (
                  <a key={g.rank} className="row" href={g.source_url ?? "#"} target="_blank" rel="noreferrer">
                    <span className={`sev-tag ${g.action_type === "diplomatic" ? "pos" : g.action_type === "security" ? "crit" : g.action_type === "fiscal" ? "high" : "mid"}`}>
                      {g.action_type ? g.action_type.toUpperCase().slice(0, 7) : "GOV"}
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

            {p1 === "protests" && (
              <>
                {protests.length === 0 && <div className="empty">// no civil unrest recorded</div>}
                {protests.slice(0, 12).map((p) => (
                  <a key={p.id} className="row" href={p.source_url ?? "#"} target="_blank" rel="noreferrer">
                    <span className={`sev-tag ${p.event_severity >= 80 ? "crit" : p.event_severity >= 60 ? "high" : "mid"}`}>
                      {p.location_name ? p.location_name.toUpperCase().slice(0, 8) : p.city ? p.city.toUpperCase().slice(0, 8) : "UNREST"}
                    </span>
                    <span className="row-main">
                      <span className="row-title clamp2">{p.headline}</span>
                      {p.llm_brief && <span className="row-sub clamp2">{p.llm_brief}</span>}
                      <span className="row-sub">
                        {p.location_level ? `[${p.location_level.toUpperCase()}] ` : ""}{p.location_name && p.location_name !== p.city ? `${p.location_name}, ` : ""}{p.state ? `${p.state} · ` : ""}{p.event_date} · Sev: {p.event_severity.toFixed(0)}/100{p.validation_source ? ` · (${p.validation_source.toUpperCase()})` : ""}
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
              <button key={t} className={p2 === t ? "btab active" : "btab"} onClick={() => setP2(t)}>
                {t === "cii" ? "CII" : t === "chokepoints" ? "CHOKEPOINTS" : t.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="bp-list">
            {p2 === "cii" && (
              <>
                {scoresArr.slice(0, 14).map(([code, score]) => (
                  <div key={code} className="row">
                    <span className={`sev-tag ${score >= 70 ? "crit" : score >= 50 ? "high" : score >= 30 ? "mid" : "pos"}`}>
                      {score.toFixed(0)}
                    </span>
                    <span className="row-main">
                      <span className="row-title">{code}</span>
                      <span className="cii-bar"><i style={{ width: `${score}%` }} className={score >= 70 ? "crit" : score >= 50 ? "high" : "mid"} /></span>
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
                    onClick={() => {
                      if (mapRef.current) {
                        mapRef.current.flyTo({ center: [cp.long, cp.lat], zoom: 5 });
                      }
                    }}
                  >
                    <span className={`sev-tag ${cp.status === "red" ? "crit" : cp.status === "yellow" ? "high" : "pos"}`}>
                      {cp.disruption_score.toFixed(0)}
                    </span>
                    <span className="row-main">
                      <span className="row-title">{cp.name} ({cp.code}) · <b className={cp.status === "red" ? "down" : cp.status === "yellow" ? "up" : "pos"}>{cp.status.toUpperCase()}</b></span>
                      <span className="row-sub">{cp.baseline_mbd} MBD baseline · {cp.last_disruption_reason || "Normal transit"}</span>
                    </span>
                  </div>
                ))}
                {chokepoints.length === 0 && <div className="empty">// awaiting chokepoints data</div>}
              </>
            )}

            {p2 === "aggression" && (
              <>
                {topAggression.map((p) => (
                  <div key={`${p.country_a}-${p.country_b}`} className="row">
                    <span className={`sev-tag ${(p.aggression_score ?? 0) >= 70 ? "crit" : (p.aggression_score ?? 0) >= 40 ? "high" : "mid"}`}>
                      {(p.aggression_score ?? 0).toFixed(0)}
                    </span>
                    <span className="row-main">
                      <span className="row-title">{p.country_a} → {p.country_b}</span>
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
                  <select className="cmd-select" value={cascadeCountry} onChange={(e) => setCascadeCountry(e.target.value)}>
                    {CASCADE_COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <span className="row-sub">contagion source · 7d window</span>
                </div>
                {cascade.slice(0, 12).map((p) => {
                  const other = p.source_country === cascadeCountry ? p.target_country : p.source_country;
                  return (
                    <div key={`${p.source_country}-${p.target_country}`} className="row">
                      <span className={`sev-tag ${p.contagion_score >= 0.6 ? "crit" : p.contagion_score >= 0.3 ? "high" : "mid"}`}>
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

            {p2 === "routes" && (
              <>
                {topRoutes.slice(0, 14).map((r) => (
                  <div
                    key={r.id}
                    className="row row-clickable"
                    onClick={() => {
                      if (mapRef.current) {
                        mapRef.current.flyTo({ center: [r.origin_long, r.origin_lat], zoom: 4 });
                      }
                    }}
                  >
                    <span className={`sev-tag ${r.risk_score >= 70 ? "crit" : r.risk_score >= 45 ? "high" : "mid"}`}>
                      {r.risk_score.toFixed(0)}
                    </span>
                    <span className="row-main">
                      <span className="row-title">{r.commodity_code} · IND → {r.partner_country}</span>
                      <span className="row-sub">via {r.primary_chokepoint ?? "direct lane"}</span>
                    </span>
                  </div>
                ))}
                {topRoutes.length === 0 && <div className="empty">// no trade routes ingested</div>}
              </>
            )}
          </div>
        </section>

        {/* Panel 3: Signals, News, Markets, Flights & Seismic */}
        <section className="bp">
          <div className="bp-head">
            <span>SIGNALS & MARKETS</span>
            <span className="bp-count">
              {p3 === "odds" ? predictions.length : p3 === "headlines" ? headlines.length : p3 === "markets" ? commodities.length + freight.length : p3 === "flights" ? flights.length : quakesNear.length}
            </span>
          </div>
          <div className="bp-tabs">
            {(["odds", "headlines", "markets", "flights", "seismic"] as const).map((t) => (
              <button key={t} className={p3 === t ? "btab active" : "btab"} onClick={() => setP3(t)}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="bp-list">
            {p3 === "odds" && (
              <>
                {predictions.slice(0, 10).map((m) => (
                  <a key={m.market_slug} className="row" href={m.url ?? "#"} target="_blank" rel="noreferrer">
                    <span className={`sev-tag ${(m.yes_price ?? 0) >= 0.5 ? "crit" : "mid"}`}>
                      {m.yes_price !== null ? `${(m.yes_price * 100).toFixed(0)}%` : "—"}
                    </span>
                    <span className="row-main">
                      <span className="row-title clamp2">{m.question}</span>
                      <span className="row-sub">polymarket · ${(m.volume_24h_usd ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}/24h</span>
                    </span>
                  </a>
                ))}
                {predictions.length === 0 && <div className="empty">// no open markets</div>}
              </>
            )}

            {p3 === "headlines" && (
              <>
                <div className="inline-select">
                  <select className="cmd-select" value={headlineRegion} onChange={(e) => setHeadlineRegion(e.target.value)}>
                    {HEADLINE_REGIONS.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ").toUpperCase()}</option>)}
                  </select>
                </div>
                {headlines.map((h) => (
                  <a key={h.id} className="row" href={h.source_url ?? "#"} target="_blank" rel="noreferrer">
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
                      <span className="row-sub">${c.price_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })} USD</span>
                    </span>
                  </div>
                ))}
                <div className="tab-section-head" style={{ marginTop: 8 }}>GLOBAL FREIGHT INDICES</div>
                {freight.map((fr) => (
                  <div key={fr.index_code} className="row">
                    <span className={`sev-tag ${(fr.change_pct ?? 0) >= 0 ? "high" : "pos"}`}>
                      {fmtPct(fr.change_pct)}
                    </span>
                    <span className="row-main">
                      <span className="row-title">{fr.name}</span>
                      <span className="row-sub">${fr.rate_usd.toLocaleString()} / FEU {fr.is_estimated ? "(est)" : ""}</span>
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
                    onClick={() => {
                      if (mapRef.current) {
                        mapRef.current.flyTo({ center: [fl.longitude, fl.latitude], zoom: 6 });
                      }
                    }}
                  >
                    <span className="sev-tag mid">{fl.aircraft_type ?? "MIL"}</span>
                    <span className="row-main">
                      <span className="row-title">{fl.callsign || fl.hex} · {fl.registration || "No Reg"}</span>
                      <span className="row-sub">
                        {fl.altitude_ft ? `${fl.altitude_ft.toLocaleString()} ft` : "ground"} · {fl.ground_speed_kt ? `${fl.ground_speed_kt.toFixed(0)} kt` : "—"} · sq {fl.squawk || "—"}
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
                    onClick={() => {
                      if (mapRef.current) {
                        mapRef.current.flyTo({ center: [q.longitude, q.latitude], zoom: 6 });
                      }
                    }}
                  >
                    <span className="sev-tag mid">M{q.magnitude.toFixed(1)}</span>
                    <span className="row-main">
                      <span className="row-title clamp2">{q.place ?? "—"}</span>
                      <span className="row-sub">{q.near_chokepoint_code} · {q.distance_to_chokepoint_km?.toFixed(0)}km · {timeAgo(q.occurred_at)} ago</span>
                    </span>
                  </div>
                ))}
                {quakesNear.length === 0 && <div className="empty">// no quakes near chokepoints</div>}
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

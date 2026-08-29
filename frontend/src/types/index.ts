export type Commodity = {
  commodity_code: string;
  name: string;
  price_usd: number;
  change_pct: number | null;
};

export type Freight = {
  index_code: string;
  name: string;
  rate_usd: number;
  change_pct: number | null;
  is_estimated: boolean;
};

export type Quake = {
  external_id: string;
  magnitude: number;
  place: string | null;
  latitude: number;
  longitude: number;
  near_chokepoint_code: string | null;
  distance_to_chokepoint_km: number | null;
  occurred_at: string;
};

export type Prediction = {
  market_slug: string;
  question: string;
  yes_price: number | null;
  volume_24h_usd: number | null;
  url: string | null;
};

export type Protest = {
  id: number;
  headline: string;
  event_date: string;
  location_name?: string | null;
  location_level?: string | null;
  state?: string | null;
  country_code?: string | null;
  city?: string | null;
  action_geo_lat?: number | null;
  action_geo_long?: number | null;
  event_severity: number;
  llm_brief?: string | null;
  source_url?: string | null;
  validation_source?: string | null;
  updated_at?: string;
};

export type FeedItem = {
  global_event_id: number;
  event_date: string;
  ingested_at: string | null;
  country_code: string | null;
  actor1_code: string | null;
  actor2_code: string | null;
  event_severity: number;
  num_mentions: number;
  source_url: string | null;
};

export type CiiScore = {
  country_code: string;
  cii_score: number;
  confidence_interval_low?: number;
  confidence_interval_high?: number;
};

export type Chokepoint = {
  code: string;
  name: string;
  lat: number;
  long: number;
  disruption_score: number;
  status: string;
  baseline_mbd: number;
  last_disruption_reason?: string | null;
};

export type TradeRoute = {
  id: number;
  commodity_code: string;
  partner_country: string;
  primary_chokepoint: string | null;
  origin_lat: number;
  origin_long: number;
  dest_lat: number;
  dest_long: number;
  dest_port_name?: string | null;
  dest_port_code?: string | null;
  risk_score: number;
};

export type AggressionPair = {
  country_a: string;
  country_b: string;
  aggression_score: number | null;
  event_count: number;
  data_source: string;
};

export type CascadePair = {
  source_country: string;
  target_country: string;
  contagion_score: number;
  co_spike_count: number;
  source_spike_count: number;
};

export type Headline = {
  id: number;
  region: string;
  rank: number;
  headline: string;
  source_url: string | null;
  llm_brief: string | null;
};

export type GovernmentAction = {
  rank: number;
  headline: string;
  action_type: string;
  gdelt_event_id: number | null;
  source_url: string | null;
  published_at: string | null;
  llm_brief: string | null;
  validation_source: string | null;
  updated_at: string;
};

export type Flight = {
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

export type IntelSite = {
  category: string;
  name: string;
  country_code: string | null;
  latitude: number;
  longitude: number;
  is_estimated: boolean;
};

export type IntelRoute = {
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

export type WorldBrief = {
  brief: string;
  generated_at: string;
  signals: {
    top_cii: [string, number][];
    events_24h: number;
    hot_chokepoints: number;
  };
  model: string;
};

export type Alert = {
  id: string;
  type: 'cii' | 'chokepoint' | 'flight' | 'seismic' | 'cascade';
  level: 'critical' | 'warning' | 'info';
  entity: string;
  value: number;
  message: string;
  timestamp: string;
};

export const REGIONS = ['usa', 'europe', 'middle_east', 'india'] as const;
export type Region = (typeof REGIONS)[number];

export const WINDOWS_H = [1, 6, 24, 48, 168] as const;

export const CASCADE_COUNTRIES = ['ISR', 'UKR', 'SYR', 'YEM', 'SDN', 'PAK', 'RUS', 'CHN'] as const;

export const HEADLINE_REGIONS = [
  'middle_east',
  'europe',
  'united_states',
  'india',
  'asia_pacific',
  'africa',
  'latin_america_australia',
] as const;

export const TV_CHANNELS = [
  { id: 'aljazeera', name: 'AL JAZEERA', url: 'https://www.youtube-nocookie.com/embed/live_stream?channel=UCfiwzLy-8yKzIbsmZTzxDgw&autoplay=1&mute=1' },
  { id: 'skynews', name: 'SKY NEWS', url: 'https://www.youtube-nocookie.com/embed/live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ&autoplay=1&mute=1' },
  { id: 'dw', name: 'DW NEWS', url: 'https://www.youtube-nocookie.com/embed/live_stream?channel=UCknLrEdhRCp1aegoMqRaCZg&autoplay=1&mute=1' },
  { id: 'france24', name: 'FRANCE 24', url: 'https://www.youtube-nocookie.com/embed/live_stream?channel=UCQfwfsi5VrQ8yKZ-UWmAEFg&autoplay=1&mute=1' },
  { id: 'euronews', name: 'EURONEWS', url: 'https://www.youtube-nocookie.com/embed/live_stream?channel=UCSrZ3UV4jOidv8ppoVuvW9Q&autoplay=1&mute=1' },
] as const;

export type NavalFleet = {
  code: string;
  name: string;
  country_code: string;
  flag_country: string;
  fleet_type: string;
  flagship: string;
  composition: string | null;
  operational_area: string;
  latitude: number;
  longitude: number;
  status: string;
  threat_level: string;
  mission_brief: string | null;
  source_citation: string | null;
  last_reported_at: string;
};

export type Panel1Tab = 'escalations' | 'gov_actions' | 'protests';
export type Panel2Tab = 'cii' | 'chokepoints' | 'aggression' | 'cascade' | 'routes';
export type Panel3Tab = 'odds' | 'headlines' | 'markets' | 'flights' | 'fleets' | 'seismic';
export type MapTheme = 'satellite' | 'dark';

export type LayerState = {
  cii: boolean;
  routes: boolean;
  quakes: boolean;
  chokes: boolean;
  protests: boolean;
  flights: boolean;
  naval: boolean;
  bases: boolean;
  nuclear: boolean;
  spaceports: boolean;
  cables: boolean;
};

export type LoadedState = {
  cii: boolean;
  quakes: boolean;
  chokes: boolean;
  protests: boolean;
  routes: boolean;
  flights: boolean;
  naval: boolean;
  intel: boolean;
};

export interface SageChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface SageChatRequest {
  message: string;
  history: SageChatMessage[];
}

export interface SageTelemetryHighlight {
  label: string;
  value: string;
}

export interface SageChatResponse {
  reply: string;
  telemetry_highlights: SageTelemetryHighlight[];
  suggested_followups: string[];
  model_used: string;
  latency_ms: number;
}

export interface SageSuggestion {
  category: string;
  emoji: string;
  prompts: string[];
}
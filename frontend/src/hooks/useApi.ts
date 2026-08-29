import { useQuery } from '@tanstack/react-query';
import type {
  FeedItem,
  CascadePair,
  Headline,
  GovernmentAction,
  Commodity,
  Freight,
  Quake,
  Prediction,
  Protest,
  Chokepoint,
  TradeRoute,
  AggressionPair,
  Flight,
  NavalFleet,
  IntelSite,
  IntelRoute,
  WorldBrief,
  CiiScore,
  Alert,
  SageChatRequest,
  SageChatResponse,
  SageSuggestion,
} from '../types';

async function api<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export function useLiveFeed(region: string, windowH: number) {
  return useQuery({
    queryKey: ['live-feed', region, windowH],
    queryFn: () => api<{ items: FeedItem[] }>(`/api/v1/live-feed/${region}?window_hours=${windowH}`),
    refetchInterval: 30000,
    staleTime: 15000,
  });
}

export function useCascade(country: string) {
  return useQuery({
    queryKey: ['cascade', country],
    queryFn: () => api<{ pairs: CascadePair[] }>(`/api/v1/cascade/${country}?window_days=7`),
    refetchInterval: 60000,
    staleTime: 30000,
    enabled: !!country,
  });
}

export function useRegionalHeadlines(region: string) {
  return useQuery({
    queryKey: ['headlines', region],
    queryFn: () => api<Headline[]>(`/api/v1/dashboard/regional-headlines?region=${region}`),
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

export function useWorldBrief(enabled: boolean) {
  return useQuery({
    queryKey: ['world-brief'],
    queryFn: () => api<WorldBrief>('/api/v1/brief/world'),
    enabled,
    staleTime: 900000,
    gcTime: 1800000,
  });
}

export function useDashboardData() {
  return useQuery({
    queryKey: ['dashboard-data'],
    queryFn: async () => {
      const [
        commodities,
        freight,
        quakes,
        predictions,
        protests,
        govActions,
        chokepoints,
        routes,
        aggression,
        flights,
        navalFleets,
        intel,
      ] = await Promise.all([
        api<Commodity[]>('/api/v1/markets/commodities'),
        api<Freight[]>('/api/v1/markets/shipping'),
        api<Quake[]>('/api/v1/events/earthquakes?hours=168&min_magnitude=4&limit=150'),
        api<Prediction[]>('/api/v1/events/prediction-markets?limit=20'),
        api<Protest[]>('/api/v1/dashboard/protests?limit=100'),
        api<GovernmentAction[]>('/api/v1/dashboard/government-actions'),
        api<Chokepoint[]>('/api/v1/dashboard/chokepoints'),
        api<TradeRoute[]>('/api/v1/dashboard/trade-routes'),
        api<{ pairs: AggressionPair[] }>('/api/v1/aggression/matrix'),
        api<Flight[]>('/api/v1/events/flights?limit=500'),
        api<NavalFleet[]>('/api/v1/events/naval'),
        api<{ sites: IntelSite[]; routes: IntelRoute[] }>('/api/v1/events/intel'),
      ]);

      return {
        commodities,
        freight,
        quakes,
        predictions,
        protests,
        govActions,
        chokepoints,
        routes,
        aggression: aggression.pairs ?? [],
        flights,
        navalFleets,
        intelSites: intel.sites ?? [],
        intelRoutes: intel.routes ?? [],
      };
    },
    refetchInterval: 30000,
    staleTime: 15000,
  });
}

export function useCIIScores() {
  return useQuery({
    queryKey: ['cii-scores'],
    queryFn: () => api<CiiScore[]>('/api/v1/cii/latest'),
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

export function useBoundaries() {
  return useQuery({
    queryKey: ['boundaries'],
    queryFn: () => api<{ iso_a3: string; geojson: object }[]>('/api/v1/dashboard/boundaries'),
    staleTime: 3600000,
    gcTime: 7200000,
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: () => api<Alert[]>('/api/v1/alerts/recent?limit=50'),
    refetchInterval: 15000,
    staleTime: 5000,
  });
}

export async function sendSageMessage(payload: SageChatRequest): Promise<SageChatResponse> {
  const res = await fetch('/api/v1/sage/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Sage request failed (${res.status})`);
  }
  return res.json() as Promise<SageChatResponse>;
}

export function useSageContext(enabled: boolean = true) {
  return useQuery({
    queryKey: ['sage-context'],
    queryFn: () => api<Record<string, unknown>>('/api/v1/sage/context'),
    enabled,
    refetchInterval: 30000,
    staleTime: 15000,
  });
}

export function useSageSuggestions(enabled: boolean = true) {
  return useQuery({
    queryKey: ['sage-suggestions'],
    queryFn: async () => {
      const res = await api<{ categories: SageSuggestion[] }>('/api/v1/sage/suggestions');
      return res.categories;
    },
    enabled,
    staleTime: Infinity,
  });
}

export async function synthesizeSageSpeech(
  text: string,
  voice?: string,
  speed?: number
): Promise<Blob> {
  const res = await fetch('/api/v1/sage/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice, speed }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Sage TTS failed (${res.status})`);
  }
  return res.blob();
}
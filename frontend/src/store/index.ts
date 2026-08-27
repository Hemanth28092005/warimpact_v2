import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  Region,
  Panel1Tab,
  Panel2Tab,
  Panel3Tab,
  MapTheme,
  LayerState,
  LoadedState,
  Alert,
} from '../types';

interface UIState {
  // Map state
  view3d: boolean;
  mapTheme: MapTheme;
  autoRotate: boolean;
  region: Region;
  windowH: number;
  cascadeCountry: string;
  headlineRegion: string;

  // Panel tabs
  p1: Panel1Tab;
  p2: Panel2Tab;
  p3: Panel3Tab;

  // Modals
  showBrief: boolean;
  showTv: boolean;
  tvChannel: string;
  tvMinimized: boolean;

  // Layers
  layers: LayerState;
  loaded: LoadedState;

  // Alerts
  alerts: Alert[];
  maxAlerts: number;

  // Actions
  setView3d: (v: boolean) => void;
  setMapTheme: (t: MapTheme) => void;
  setAutoRotate: (v: boolean) => void;
  setRegion: (r: Region) => void;
  setWindowH: (h: number) => void;
  setCascadeCountry: (c: string) => void;
  setHeadlineRegion: (r: string) => void;
  setP1: (t: Panel1Tab) => void;
  setP2: (t: Panel2Tab) => void;
  setP3: (t: Panel3Tab) => void;
  setShowBrief: (v: boolean) => void;
  setShowTv: (v: boolean) => void;
  setTvChannel: (c: string) => void;
  setTvMinimized: (v: boolean) => void;
  toggleLayer: (k: keyof LayerState) => void;
  setLoaded: (k: keyof LoadedState, v: boolean) => void;
  addAlert: (alert: Alert) => void;
  clearAlerts: () => void;
}

const defaultLayers: LayerState = {
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
};

const defaultLoaded: LoadedState = {
  cii: false,
  quakes: false,
  chokes: false,
  protests: false,
  routes: false,
  flights: false,
  intel: false,
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      view3d: true,
      mapTheme: 'satellite',
      autoRotate: false,
      region: 'middle_east',
      windowH: 168,
      cascadeCountry: 'ISR',
      headlineRegion: 'middle_east',
      p1: 'escalations',
      p2: 'cii',
      p3: 'odds',
      showBrief: false,
      showTv: false,
      tvChannel: 'aljazeera',
      tvMinimized: false,
      layers: defaultLayers,
      loaded: defaultLoaded,
      alerts: [],
      maxAlerts: 50,

      setView3d: (v) => set({ view3d: v }),
      setMapTheme: (t) => set({ mapTheme: t }),
      setAutoRotate: (v) => set({ autoRotate: v }),
      setRegion: (r) => set({ region: r }),
      setWindowH: (h) => set({ windowH: h }),
      setCascadeCountry: (c) => set({ cascadeCountry: c }),
      setHeadlineRegion: (r) => set({ headlineRegion: r }),
      setP1: (t) => set({ p1: t }),
      setP2: (t) => set({ p2: t }),
      setP3: (t) => set({ p3: t }),
      setShowBrief: (v) => set({ showBrief: v }),
      setShowTv: (v) => set({ showTv: v }),
      setTvChannel: (c) => set({ tvChannel: c }),
      setTvMinimized: (v) => set({ tvMinimized: v }),
      toggleLayer: (k) =>
        set((s) => ({
          layers: { ...(s.layers || defaultLayers), [k]: !(s.layers || defaultLayers)[k] },
        })),
      setLoaded: (k, v) =>
        set((s) => ({ loaded: { ...(s.loaded || defaultLoaded), [k]: v } })),
      addAlert: (alert) =>
        set((s) => ({
          alerts: [alert, ...(s.alerts || []).slice(0, (s.maxAlerts || 50) - 1)],
        })),
      clearAlerts: () => set({ alerts: [] }),
    }),
    {
      name: "war-monitor-ui-v2",
      partialize: (state) => ({
        view3d: state.view3d,
        mapTheme: state.mapTheme,
        region: state.region,
        windowH: state.windowH,
        layers: state.layers,
      }),
    }
  )
);
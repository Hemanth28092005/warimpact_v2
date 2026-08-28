import React, { useMemo } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

import { useUIStore } from "./store";
import {
  useDashboardData,
  useCIIScores,
  useBoundaries,
  useLiveFeed,
  useCascade,
  useRegionalHeadlines,
  useWorldBrief,
  useAlerts,
} from "./hooks/useApi";
import { defcon } from "./utils/formatters";

import { CommandBar } from "./components/CommandBar";
import { HeroBanner } from "./components/HeroBanner";
import { SitBar } from "./components/SitBar";
import { GlobeView } from "./components/GlobeView";
import { BottomPanels } from "./components/BottomPanels";
import { TVPanel } from "./components/TVPanel";
import { AIBriefModal } from "./components/AIBriefModal";
import { AlertsPanel } from "./components/AlertsPanel";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function WarMonitorApp(): JSX.Element {
  const {
    region,
    windowH,
    cascadeCountry,
    headlineRegion,
    showBrief,
    setShowBrief,
  } = useUIStore();

  // Queries
  const { data: dashboardData, isLoading: dashLoading } = useDashboardData();
  const { data: ciiScoresData } = useCIIScores();
  const { data: boundariesData = [] } = useBoundaries();
  const { data: liveFeedData } = useLiveFeed(region, windowH);
  const { data: cascadeData } = useCascade(cascadeCountry);
  const { data: headlinesData = [] } = useRegionalHeadlines(headlineRegion);
  const {
    data: briefData,
    isLoading: briefLoading,
    error: briefErrorObj,
    refetch: refetchBrief,
  } = useWorldBrief(showBrief);
  const { data: alertsData = [] } = useAlerts();

  // Derived state
  const commodities = dashboardData?.commodities ?? [];
  const freight = dashboardData?.freight ?? [];
  const quakes = dashboardData?.quakes ?? [];
  const predictions = dashboardData?.predictions ?? [];
  const protests = dashboardData?.protests ?? [];
  const govActions = dashboardData?.govActions ?? [];
  const chokepoints = dashboardData?.chokepoints ?? [];
  const routes = dashboardData?.routes ?? [];
  const aggression = dashboardData?.aggression ?? [];
  const flights = dashboardData?.flights ?? [];
  const intelSites = dashboardData?.intelSites ?? [];
  const intelRoutes = dashboardData?.intelRoutes ?? [];

  const feed = liveFeedData?.items ?? [];
  const cascade = cascadeData?.pairs ?? [];

  const ciiScores = useMemo(() => {
    const map = new Map<string, number>();
    if (ciiScoresData) {
      ciiScoresData.forEach((s) => map.set(s.country_code, s.cii_score));
    }
    return map;
  }, [ciiScoresData]);

  const scoresArr = useMemo(() => {
    return Array.from(ciiScores.entries()).sort((a, b) => b[1] - a[1]);
  }, [ciiScores]);

  const avgCii = useMemo(() => {
    return scoresArr.length
      ? scoresArr.reduce((a, [, v]) => a + v, 0) / scoresArr.length
      : null;
  }, [scoresArr]);

  const defconLevel = defcon(avgCii);

  const quakesNear = useMemo(() => {
    return quakes.filter((q) => q.near_chokepoint_code);
  }, [quakes]);

  const topAggression = useMemo(() => {
    return aggression
      .filter((p) => p.event_count !== null && p.data_source === "gdelt_derived")
      .sort((a, b) => (b.event_count ?? 0) - (a.event_count ?? 0))
      .slice(0, 10);
  }, [aggression]);

  const topRoutes = useMemo(() => {
    return [...routes].sort((a, b) => b.risk_score - a.risk_score);
  }, [routes]);

  const loaded = {
    cii: !dashLoading && ciiScores.size > 0,
    quakes: !dashLoading && quakes.length > 0,
    chokes: !dashLoading && chokepoints.length > 0,
    protests: !dashLoading && protests.length > 0,
    routes: !dashLoading && routes.length > 0,
    flights: !dashLoading && flights.length > 0,
    intel: !dashLoading && intelSites.length > 0,
  };

  return (
    <div className="app">
      <CommandBar defconLevel={defconLevel} />
      <HeroBanner alerts={alertsData} avgCii={avgCii} defconLevel={defconLevel} />
      <SitBar
        escalationsCount={feed.length}
        govActionsCount={govActions.length}
        flightsCount={flights.length}
        chokeAlertsCount={chokepoints.filter((c) => c.status !== "green").length}
        commodities={commodities}
      />

      <GlobeView
        boundariesData={boundariesData}
        ciiScores={ciiScores}
        quakes={quakes}
        protests={protests}
        chokepoints={chokepoints}
        routes={routes}
        flights={flights}
        intelSites={intelSites}
        intelRoutes={intelRoutes}
        loaded={loaded}
      />

      <TVPanel />

      <AIBriefModal
        showBrief={showBrief}
        onClose={() => setShowBrief(false)}
        briefData={briefData}
        briefLoading={briefLoading}
        briefError={briefErrorObj ? String(briefErrorObj) : null}
        onRefresh={() => refetchBrief()}
      />

      <BottomPanels
        feed={feed}
        govActions={govActions}
        protests={protests}
        scoresArr={scoresArr}
        chokepoints={chokepoints}
        topAggression={topAggression}
        cascade={cascade}
        topRoutes={topRoutes}
        predictions={predictions}
        headlines={headlinesData}
        commodities={commodities}
        freight={freight}
        flights={flights}
        quakesNear={quakesNear}
      />
    </div>
  );
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("WarMonitor uncaught component error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "40px 20px", color: "#ff6b6b", background: "#010308", fontFamily: "monospace", minHeight: "100vh" }}>
          <h2>SYSTEM DISPLAY EXCEPTION</h2>
          <p>{this.state.error?.message}</p>
          <button
            style={{ padding: "8px 16px", background: "#22d3ee", color: "#000", border: "none", cursor: "pointer", fontWeight: 700, marginTop: "16px" }}
            onClick={() => {
              localStorage.clear();
              window.location.reload();
            }}
          >
            RESET LOCAL STATE & RELOAD
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <WarMonitorApp />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

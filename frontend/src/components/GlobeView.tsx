import React, { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useUIStore } from "../store";
import {
  WINDOWS_H,
  Quake,
  Protest,
  Chokepoint,
  TradeRoute,
  Flight,
  NavalFleet,
  IntelSite,
  IntelRoute,
} from "../types";
import { greatCircle, showPopup, INDIAN_PORTS } from "../utils/geo";
import { getIndiaPortName, getIndiaPortCode } from "../utils/format";

interface GlobeViewProps {
  boundariesData?: { iso_a3: string; geojson: object }[];
  ciiScores?: Map<string, number>;
  quakes?: Quake[];
  protests?: Protest[];
  chokepoints?: Chokepoint[];
  routes?: TradeRoute[];
  flights?: Flight[];
  navalFleets?: NavalFleet[];
  intelSites?: IntelSite[];
  intelRoutes?: IntelRoute[];
  loaded?: {
    cii: boolean;
    quakes: boolean;
    chokes: boolean;
    protests: boolean;
    routes: boolean;
    flights: boolean;
    naval: boolean;
    intel: boolean;
  };
}

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
        "raster-opacity": 1.0,
        "raster-brightness-max": 0.95,
        "raster-contrast": 0.22,
        "raster-saturation": 0.05,
      },
    },
  ],
};

const DARK_TACTICAL_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

export const GlobeView: React.FC<GlobeViewProps> = ({
  boundariesData = [],
  ciiScores = new Map(),
  quakes = [],
  protests = [],
  chokepoints = [],
  routes = [],
  flights = [],
  navalFleets = [],
  intelSites = [],
  intelRoutes = [],
  loaded = {
    cii: true,
    quakes: true,
    chokes: true,
    protests: true,
    routes: true,
    flights: true,
    naval: true,
    intel: true,
  },
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const {
    view3d,
    mapTheme,
    autoRotate,
    windowH,
    setWindowH,
    layers,
    toggleLayer,
    selectedPort,
    setSelectedPort,
  } = useUIStore();

  // 1. Initialize Map directly on DOM ref
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const styleObj = mapTheme === "satellite" ? REALISTIC_SATELLITE_STYLE : DARK_TACTICAL_STYLE;
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: styleObj,
      center: [42, 26],
      zoom: view3d ? 1.6 : 2,
      attributionControl: false,
      maxPitch: 85,
    });
    mapRef.current = map;

    map.on("style.load", () => {
      try {
        map.setProjection({ type: view3d ? "globe" : "mercator" });
      } catch (err) {
        console.warn("Projection load error:", err);
      }
    });

    return () => {
      try {
        map.remove();
      } catch (err) {
        console.warn("Map remove error:", err);
      }
      mapRef.current = null;
    };
  }, [mapTheme]);

  // 2. View 3D Projection update
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const updateProj = () => {
      try {
        map.setProjection({ type: view3d ? "globe" : "mercator" });
      } catch (err) {
        console.warn("Projection update error:", err);
      }
    };
    if (map.isStyleLoaded()) {
      updateProj();
    } else {
      map.once("style.load", updateProj);
    }
  }, [view3d]);

  // 3. Orbit Rotation
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
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

  // 4. Render & Update all Dynamic Layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      if (!map || !map.isStyleLoaded()) return;

      try {
        // 1. Quakes
        const quakeData = {
          type: "FeatureCollection" as const,
          features: quakes.map((q) => ({
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [q.longitude, q.latitude] },
            properties: { mag: q.magnitude, place: q.place ?? "", id: q.external_id },
          })),
        };
        if (!map.getSource("quakes") && loaded.quakes && quakes.length > 0) {
          map.addSource("quakes", { type: "geojson", data: quakeData as never });
          map.addLayer({
            id: "quake-circles",
            type: "circle",
            source: "quakes",
            paint: {
              "circle-radius": [
                "interpolate", ["linear"], ["get", "mag"],
                4, 3, 5, 6, 6, 11, 7, 18, 8, 26,
              ],
              "circle-color": [
                "interpolate", ["linear"], ["get", "mag"],
                4, "rgba(250,204,21,0.7)", 5.5, "rgba(249,115,22,0.85)", 7, "rgba(239,68,68,0.95)",
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.2,
              "circle-opacity": 0.88,
            },
          });
          map.on("click", "quake-circles", (e) => {
            const f = e.features?.[0];
            if (!f) return;
            showPopup(map, e.lngLat, `<div class="wm-pop"><span class="wm-pop-code">M${Number(f.properties?.mag).toFixed(1)}</span> SEISMIC EVENT<br/>${f.properties?.place || "Offshore"}</div>`);
          });
        } else if (map.getSource("quakes")) {
          (map.getSource("quakes") as maplibregl.GeoJSONSource).setData(quakeData as never);
        }

        // 2. Protests & Civil Unrest
        const protestData = {
          type: "FeatureCollection" as const,
          features: protests.filter((p) => p.action_geo_lat !== null && p.action_geo_long !== null).map((p) => ({
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [p.action_geo_long!, p.action_geo_lat!] },
            properties: {
              headline: p.headline,
              city: p.city || p.location_name || "",
              loc: p.location_name || p.city || "",
              sev: p.event_severity,
              source: p.validation_source || "gdelt",
            },
          })),
        };
        if (!map.getSource("protests") && loaded.protests && protests.length > 0) {
          map.addSource("protests", { type: "geojson", data: protestData as never });
          map.addLayer({
            id: "protest-circles",
            type: "circle",
            source: "protests",
            paint: {
              "circle-radius": [
                "interpolate", ["linear"], ["get", "sev"],
                20, 3.5, 50, 6, 80, 11, 100, 15,
              ],
              "circle-color": [
                "interpolate", ["linear"], ["get", "sev"],
                0, "rgba(251,191,36,0.8)", 50, "rgba(249,115,22,0.9)", 75, "rgba(239,68,68,0.95)",
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1,
              "circle-opacity": 0.9,
            },
          });
          map.on("click", "protest-circles", (e) => {
            const f = e.features?.[0];
            if (!f) return;
            showPopup(map, e.lngLat, `<div class="wm-pop"><span class="wm-pop-dim">${f.properties?.loc}</span><br/>${f.properties?.headline}</div>`);
          });
        } else if (map.getSource("protests")) {
          (map.getSource("protests") as maplibregl.GeoJSONSource).setData(protestData as never);
        }

        // 3. Trade routes
        const activeRoutes = selectedPort === "ALL"
          ? routes
          : routes.filter((r) => getIndiaPortCode(r.dest_lat, r.dest_long) === selectedPort);

        const routeData = {
          type: "FeatureCollection" as const,
          features: activeRoutes.map((r) => ({
            type: "Feature" as const,
            geometry: {
              type: "LineString" as const,
              coordinates: greatCircle([r.origin_long, r.origin_lat], [r.dest_long, r.dest_lat]),
            },
            properties: {
              risk: r.risk_score,
              commodity: r.commodity_code,
              partner: r.partner_country,
              port: getIndiaPortName(r.dest_lat, r.dest_long),
              choke: r.primary_chokepoint ?? "direct",
              color: r.risk_score >= 80 ? "#ef4444" : r.risk_score >= 60 ? "#f97316" : r.risk_score >= 35 ? "#eab308" : "#22d3ee",
            },
          })),
        };

        if (!map.getSource("trade-routes") && loaded.routes && routes.length > 0) {
          map.addSource("trade-routes", { type: "geojson", data: routeData as never });
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
            showPopup(
              map,
              e.lngLat,
              `<div class="wm-pop"><span class="wm-pop-code">${f.properties?.commodity}</span><br/>${f.properties?.partner} ⇄ <b>${f.properties?.port || "India Gateway"}</b><br/>risk <b>${Number(f.properties?.risk).toFixed(1)}</b>/100<br/><span class="wm-pop-dim">via ${f.properties?.choke ?? "direct corridor"}</span></div>`
            );
          };
          map.on("click", "route-lines-base", handleRouteClick);
          map.on("click", "route-lines-active", handleRouteClick);
        } else if (map.getSource("trade-routes")) {
          (map.getSource("trade-routes") as maplibregl.GeoJSONSource).setData(routeData as never);
        }

        // 3b. Indian Commercial Destination Landing Ports (Designated Trade Gateways)
        const portData = {
          type: "FeatureCollection" as const,
          features: INDIAN_PORTS.map((p) => {
            const landingRoutes = routes.filter((r) => getIndiaPortCode(r.dest_lat, r.dest_long) === p.code);
            const commodities = Array.from(new Set(landingRoutes.map((r) => r.commodity_code.replace(/_/g, " ")))).join(", ") || p.commodities;
            const partners = Array.from(new Set(landingRoutes.map((r) => r.partner_country))).join(", ") || "Global Trade";
            const chokes = Array.from(new Set(landingRoutes.map((r) => r.primary_chokepoint).filter(Boolean))).join(", ") || "Direct Coastal";
            const avgRisk = landingRoutes.length > 0
              ? (landingRoutes.reduce((acc, r) => acc + r.risk_score, 0) / landingRoutes.length).toFixed(1)
              : "32.0";

            return {
              type: "Feature" as const,
              geometry: { type: "Point" as const, coordinates: [p.long, p.lat] },
              properties: {
                code: p.code,
                name: p.name,
                state: p.state,
                commodities: commodities,
                partners: partners,
                chokes: chokes,
                avgRisk: avgRisk,
                landingCount: landingRoutes.length,
                label: landingRoutes.length > 0 ? `⚓ ${p.name} (${landingRoutes.length})` : `⚓ ${p.name}`,
                trafficType: p.trafficType,
              },
            };
          }),
        };
        if (!map.getSource("india-ports")) {
          map.addSource("india-ports", { type: "geojson", data: portData as never });
          map.addLayer({
            id: "port-pulse-glow",
            type: "circle",
            source: "india-ports",
            paint: {
              "circle-radius": [
                "case",
                ["==", ["get", "code"], selectedPort],
                ["interpolate", ["linear"], ["zoom"], 1, 10, 4, 18, 8, 26],
                ["interpolate", ["linear"], ["zoom"], 1, 5.0, 4, 9.0, 8, 15],
              ],
              "circle-color": [
                "case",
                ["==", ["get", "code"], selectedPort],
                "#00f0ff",
                "#22d3ee",
              ],
              "circle-opacity": [
                "case",
                ["==", ["get", "code"], selectedPort],
                0.95,
                0.6,
              ],
              "circle-blur": 0.35,
            },
          });
          map.addLayer({
            id: "port-circle-outer",
            type: "circle",
            source: "india-ports",
            paint: {
              "circle-radius": [
                "case",
                ["==", ["get", "code"], selectedPort],
                ["interpolate", ["linear"], ["zoom"], 1, 5.0, 4, 7.5, 8, 10.0],
                ["interpolate", ["linear"], ["zoom"], 1, 3.5, 4, 5.0, 8, 8.0],
              ],
              "circle-color": [
                "case",
                ["==", ["get", "code"], selectedPort],
                "#00f0ff",
                "#0284c7",
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": [
                "case",
                ["==", ["get", "code"], selectedPort],
                2.5,
                1.5,
              ],
              "circle-opacity": 1.0,
            },
          });
          map.addLayer({
            id: "port-labels",
            type: "symbol",
            source: "india-ports",
            layout: {
              "text-field": ["get", "label"],
              "text-size": ["interpolate", ["linear"], ["zoom"], 1, 8, 4, 10, 8, 12],
              "text-offset": [0, 1.2],
              "text-anchor": "top",
              "text-allow-overlap": false,
              "text-ignore-placement": false,
            },
            paint: {
              "text-color": [
                "case",
                ["==", ["get", "code"], selectedPort],
                "#00f0ff",
                "#38bdf8",
              ],
              "text-halo-color": "#020617",
              "text-halo-width": 2.0,
            },
          });

          const handlePortMarkerClick = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
            const f = e.features?.[0];
            if (!f) return;
            const props = f.properties || {};
            const riskVal = Number(props.avgRisk) || 0;
            const riskColor = riskVal >= 60 ? "#ef4444" : riskVal >= 40 ? "#f97316" : "#22c55e";

            showPopup(
              map,
              e.lngLat,
              `<div class="wm-pop" style="min-width: 240px; font-family: monospace;">
                <div style="font-size: 9px; font-weight: 700; color: #38bdf8; letter-spacing: 0.8px; margin-bottom: 2px;">⚓ DESTINATION LANDING PORT</div>
                <div style="font-size: 13px; font-weight: 700; color: #f8fafc; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">${props.name} <span style="font-size: 10px; color: #94a3b8;">[${props.code}]</span></div>
                <div style="font-size: 10.5px; color: #93c5fd; margin-bottom: 4px;"><b>State:</b> ${props.state} · <i>${props.trafficType}</i></div>
                <div style="font-size: 10.5px; color: #e2e8f0; margin-bottom: 4px;"><b>Active Landings:</b> <span style="color: #00f0ff; font-weight: 700;">${props.landingCount} Inbound Trade Routes</span></div>
                <div style="font-size: 10px; color: #cbd5e1; margin-bottom: 4px; line-height: 1.35;"><b>Landing Commodities:</b><br/><span style="color: #fef08a;">${props.commodities}</span></div>
                <div style="font-size: 10px; color: #cbd5e1; margin-bottom: 4px;"><b>Origin Partners:</b> ${props.partners}</div>
                <div style="font-size: 10px; color: #cbd5e1; margin-bottom: 4px;"><b>Avg Route Risk:</b> <b style="color: ${riskColor};">${props.avgRisk}/100</b></div>
                <div style="font-size: 9px; color: #64748b; margin-top: 4px; border-top: 1px dashed rgba(255,255,255,0.08); padding-top: 4px;">Transit Corridors: ${props.chokes}</div>
              </div>`
            );
          };
          map.on("click", "port-circle-outer", handlePortMarkerClick);
          map.on("click", "port-labels", handlePortMarkerClick);
        } else if (map.getSource("india-ports")) {
          (map.getSource("india-ports") as maplibregl.GeoJSONSource).setData(portData as never);
        }

const ensurePlaneIcon = (map: maplibregl.Map) => {
  if (map.hasImage("plane-icon")) return;

  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, size, size);

  // Subtle glow
  ctx.shadowColor = "rgba(0, 229, 255, 0.9)";
  ctx.shadowBlur = 8;

  // Draw military jet silhouette
  ctx.fillStyle = "#00e5ff";
  ctx.strokeStyle = "#020617";
  ctx.lineWidth = 2.4;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  ctx.beginPath();
  // Nose
  ctx.moveTo(24, 4);
  // Right wing
  ctx.lineTo(27, 16);
  ctx.lineTo(44, 25);
  ctx.lineTo(44, 28);
  ctx.lineTo(27, 26);
  // Right stabilizer
  ctx.lineTo(27, 36);
  ctx.lineTo(36, 42);
  ctx.lineTo(36, 45);
  // Tail center
  ctx.lineTo(24, 42);
  // Left stabilizer
  ctx.lineTo(12, 45);
  ctx.lineTo(12, 42);
  ctx.lineTo(21, 36);
  // Left wing
  ctx.lineTo(21, 26);
  ctx.lineTo(4, 28);
  ctx.lineTo(4, 25);
  ctx.lineTo(21, 16);
  ctx.closePath();

  ctx.fill();
  ctx.stroke();

  // Cockpit canopy highlight
  ctx.beginPath();
  ctx.moveTo(24, 11);
  ctx.lineTo(24, 20);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.stroke();

  const imgData = ctx.getImageData(0, 0, size, size);
  try {
    if (!map.hasImage("plane-icon")) {
      map.addImage("plane-icon", imgData, { pixelRatio: 2 });
    }
  } catch (err) {
    console.warn("Error adding plane icon:", err);
  }
};

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
          ensurePlaneIcon(map);
          map.addSource("military-flights", { type: "geojson", data: flightData as never });
          map.addLayer({
            id: "flight-glow",
            type: "circle",
            source: "military-flights",
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2, 4, 3.5, 8, 6],
              "circle-color": "#00e5ff",
              "circle-opacity": 0.45,
              "circle-blur": 0.6,
            },
          });
          map.addLayer({
            id: "flight-icons",
            type: "symbol",
            source: "military-flights",
            layout: {
              "icon-image": "plane-icon",
              "icon-size": ["interpolate", ["linear"], ["zoom"], 1, 0.45, 3, 0.65, 6, 0.85, 9, 1.1],
              "icon-allow-overlap": true,
              "icon-ignore-placement": true,
              "icon-rotation-alignment": "map",
            },
          });
          map.on("click", "flight-icons", (e) => {
            const f = e.features?.[0];
            if (!f) return;
            showPopup(map, e.lngLat, `
              <div class="wm-pop">
                <span class="wm-pop-code">${f.properties?.callsign}</span> (${f.properties?.type})<br/>
                <b>MILITARY FLIGHT</b> · SQUAWK ${f.properties?.squawk || "—"}<br/>
                <span class="wm-pop-dim">Alt: ${f.properties?.alt ? `${f.properties?.alt} ft` : "—"} | Spd: ${f.properties?.spd ? `${f.properties?.spd} kt` : "—"}</span>
              </div>
            `);
          });
          map.on("mouseenter", "flight-icons", () => {
            map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", "flight-icons", () => {
            map.getCanvas().style.cursor = "";
          });
        } else if (map.getSource("military-flights")) {
          ensurePlaneIcon(map);
          (map.getSource("military-flights") as maplibregl.GeoJSONSource).setData(flightData as never);
        }

const ensureNavalIcon = (map: maplibregl.Map) => {
  if (map.hasImage("naval-icon")) return;

  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, size, size);

  // Tactical glow
  ctx.shadowColor = "rgba(56, 189, 248, 0.9)";
  ctx.shadowBlur = 8;

  // Warship hull drawing
  ctx.fillStyle = "#38bdf8";
  ctx.strokeStyle = "#020617";
  ctx.lineWidth = 2.4;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  ctx.beginPath();
  // Bow (Nose of warship)
  ctx.moveTo(24, 4);
  // Starboard bow flare
  ctx.lineTo(32, 14);
  // Starboard hull
  ctx.lineTo(33, 38);
  // Starboard stern quarter
  ctx.lineTo(30, 44);
  // Transom
  ctx.lineTo(18, 44);
  // Port stern quarter
  ctx.lineTo(15, 38);
  // Port hull
  ctx.lineTo(16, 14);
  ctx.closePath();

  ctx.fill();
  ctx.stroke();

  // Superstructure / Runway line
  ctx.beginPath();
  ctx.moveTo(22, 12);
  ctx.lineTo(22, 38);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.stroke();

  // Radar / Bridge island
  ctx.fillStyle = "#f59e0b";
  ctx.fillRect(26, 20, 5, 10);
  ctx.strokeStyle = "#020617";
  ctx.lineWidth = 1.2;
  ctx.strokeRect(26, 20, 5, 10);

  const imgData = ctx.getImageData(0, 0, size, size);
  try {
    if (!map.hasImage("naval-icon")) {
      map.addImage("naval-icon", imgData, { pixelRatio: 2 });
    }
  } catch (err) {
    console.warn("Error adding naval icon:", err);
  }
};

        // 4b. Strategic Naval Fleets & Strike Groups
        const navalData = {
          type: "FeatureCollection" as const,
          features: navalFleets.map((nf) => ({
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [nf.longitude, nf.latitude] },
            properties: {
              code: nf.code,
              name: nf.name,
              country_code: nf.country_code,
              flag_country: nf.flag_country,
              fleet_type: nf.fleet_type,
              flagship: nf.flagship,
              composition: nf.composition,
              operational_area: nf.operational_area,
              status: nf.status,
              threat_level: nf.threat_level,
              mission_brief: nf.mission_brief,
              source_citation: nf.source_citation,
            },
          })),
        };
        if (!map.getSource("naval-fleets") && loaded.naval && navalFleets.length > 0) {
          ensureNavalIcon(map);
          map.addSource("naval-fleets", { type: "geojson", data: navalData as never });
          map.addLayer({
            id: "naval-fleet-glow",
            type: "circle",
            source: "naval-fleets",
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3.5, 4, 6, 8, 9],
              "circle-color": [
                "case",
                ["==", ["get", "threat_level"], "critical"],
                "#ef4444",
                ["==", ["get", "threat_level"], "elevated"],
                "#f59e0b",
                "#38bdf8",
              ],
              "circle-opacity": 0.45,
              "circle-blur": 0.6,
            },
          });
          map.addLayer({
            id: "naval-fleet-icons",
            type: "symbol",
            source: "naval-fleets",
            layout: {
              "icon-image": "naval-icon",
              "icon-size": ["interpolate", ["linear"], ["zoom"], 1, 0.45, 3, 0.65, 6, 0.85, 9, 1.1],
              "icon-allow-overlap": true,
              "icon-ignore-placement": true,
              "icon-rotation-alignment": "map",
            },
          });
          map.addLayer({
            id: "naval-fleet-labels",
            type: "symbol",
            source: "naval-fleets",
            layout: {
              "text-field": ["get", "flagship"],
              "text-size": ["interpolate", ["linear"], ["zoom"], 1, 8, 4, 10, 8, 12],
              "text-offset": [0, 1.3],
              "text-anchor": "top",
              "text-allow-overlap": false,
              "text-ignore-placement": false,
            },
            paint: {
              "text-color": "#38bdf8",
              "text-halo-color": "#020617",
              "text-halo-width": 1.5,
            },
          });

          const handleNavalClick = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
            const f = e.features?.[0];
            if (!f) return;
            showPopup(
              map,
              e.lngLat,
              `
              <div class="wm-pop">
                <span class="wm-pop-code">${f.properties?.flagship}</span> (${f.properties?.country_code})<br/>
                <b>${f.properties?.name}</b> · <span class="sev-tag ${f.properties?.threat_level === 'critical' ? 'crit' : f.properties?.threat_level === 'elevated' ? 'high' : 'mid'}">${String(f.properties?.status || '').toUpperCase()}</span><br/>
                <span class="wm-pop-dim">
                  Area: <b>${f.properties?.operational_area}</b><br/>
                  ${f.properties?.composition ? `Units: ${f.properties?.composition}<br/>` : ''}
                  ${f.properties?.mission_brief ? `${f.properties?.mission_brief}` : ''}
                </span>
              </div>
            `
            );
          };

          map.on("click", "naval-fleet-icons", handleNavalClick);
          map.on("click", "naval-fleet-labels", handleNavalClick);
          map.on("mouseenter", "naval-fleet-icons", () => {
            map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", "naval-fleet-icons", () => {
            map.getCanvas().style.cursor = "";
          });
        } else if (map.getSource("naval-fleets")) {
          ensureNavalIcon(map);
          (map.getSource("naval-fleets") as maplibregl.GeoJSONSource).setData(navalData as never);
        }

        // 5. Strategic Intel Sites
        const siteFeatures = intelSites.map((s) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [s.longitude, s.latitude] },
          properties: { cat: s.category, name: s.name, cc: s.country_code },
        }));
        const siteData = { type: "FeatureCollection" as const, features: siteFeatures };
        if (!map.getSource("intel-sites") && loaded.intel && intelSites.length > 0) {
          map.addSource("intel-sites", { type: "geojson", data: siteData as never });
          map.addLayer({
            id: "intel-bases-layer",
            type: "circle",
            source: "intel-sites",
            filter: ["==", ["get", "cat"], "military_base"],
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2.5, 4, 4.5, 8, 8],
              "circle-color": "#3b82f6",
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1,
              "circle-opacity": 0.9,
            },
          });
          map.addLayer({
            id: "intel-nuclear-layer",
            type: "circle",
            source: "intel-sites",
            filter: ["==", ["get", "cat"], "nuclear_site"],
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3.5, 4, 5.5, 8, 9],
              "circle-color": "#eab308",
              "circle-stroke-color": "#000000",
              "circle-stroke-width": 1.2,
              "circle-opacity": 0.95,
            },
          });
          map.addLayer({
            id: "intel-spaceports-layer",
            type: "circle",
            source: "intel-sites",
            filter: ["==", ["get", "cat"], "spaceport"],
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3, 4, 5, 8, 8],
              "circle-color": "#a855f7",
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1,
              "circle-opacity": 0.9,
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

        // 7. Strategic Maritime Chokepoints (WebGL Native Layer with 3D Globe Depth Occlusion)
        const chokeData = {
          type: "FeatureCollection" as const,
          features: chokepoints.map((cp) => {
            const color =
              cp.status === "critical"
                ? "#ef4444"
                : cp.status === "elevated"
                ? "#f97316"
                : cp.status === "watch"
                ? "#eab308"
                : "#22c55e";
            return {
              type: "Feature" as const,
              geometry: { type: "Point" as const, coordinates: [cp.long, cp.lat] },
              properties: {
                code: cp.code,
                name: cp.name,
                status: cp.status,
                score: cp.disruption_score,
                oil: cp.baseline_mbd ?? 0,
                reason: cp.last_disruption_reason ?? "",
                color,
              },
            };
          }),
        };
        if (!map.getSource("chokepoint-points") && loaded.chokes && chokepoints.length > 0) {
          map.addSource("chokepoint-points", { type: "geojson", data: chokeData as never });
          map.addLayer({
            id: "choke-pulse-glow",
            type: "circle",
            source: "chokepoint-points",
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 6, 4, 10, 8, 16],
              "circle-color": ["get", "color"],
              "circle-opacity": 0.45,
              "circle-blur": 0.45,
            },
          });
          map.addLayer({
            id: "choke-circles",
            type: "circle",
            source: "chokepoint-points",
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3.2, 4, 5, 8, 8],
              "circle-color": "#ffffff",
              "circle-stroke-color": ["get", "color"],
              "circle-stroke-width": 2,
              "circle-opacity": 1.0,
            },
          });
          map.addLayer({
            id: "choke-labels",
            type: "symbol",
            source: "chokepoint-points",
            layout: {
              "text-field": ["get", "name"],
              "text-size": ["interpolate", ["linear"], ["zoom"], 1, 9, 4, 11, 8, 13],
              "text-offset": [0, 1.2],
              "text-anchor": "top",
              "text-allow-overlap": false,
              "text-ignore-placement": false,
            },
            paint: {
              "text-color": "#f8fafc",
              "text-halo-color": "#020617",
              "text-halo-width": 1.5,
            },
          });
          const handleChokeClick = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
            const f = e.features?.[0];
            if (!f) return;
            showPopup(
              map,
              e.lngLat,
              `<div class="wm-pop"><span class="wm-pop-code">${f.properties?.name}</span> (${f.properties?.code})<br/>Disruption: <b>${Number(f.properties?.score).toFixed(0)}</b>/100 [${String(f.properties?.status || "").toUpperCase()}]<br/><span class="wm-pop-dim">Baseline: ${f.properties?.oil} MBD ${f.properties?.reason ? `| ${f.properties?.reason}` : ""}</span></div>`
            );
          };
          map.on("click", "choke-circles", handleChokeClick);
          map.on("click", "choke-labels", handleChokeClick);
        } else if (map.getSource("chokepoint-points")) {
          (map.getSource("chokepoint-points") as maplibregl.GeoJSONSource).setData(chokeData as never);
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
        vis("port-pulse-glow", layers.routes);
        vis("port-circle-outer", layers.routes);
        vis("port-labels", layers.routes);
        vis("flight-glow", layers.flights);
        vis("flight-icons", layers.flights);
        vis("naval-fleet-glow", layers.naval);
        vis("naval-fleet-icons", layers.naval);
        vis("naval-fleet-labels", layers.naval);
        vis("intel-bases-layer", layers.bases);
        vis("intel-nuclear-layer", layers.nuclear);
        vis("intel-spaceports-layer", layers.spaceports);
        vis("intel-routes-lines", layers.cables);
        vis("choke-pulse-glow", layers.chokes);
        vis("choke-circles", layers.chokes);
        vis("choke-labels", layers.chokes);
      } catch (err) {
        console.warn("Error applying layers:", err);
      }
    };

    if (map.isStyleLoaded()) {
      apply();
    } else {
      map.once("load", apply);
    }
  }, [layers, quakes, protests, routes, flights, navalFleets, chokepoints, intelSites, intelRoutes, loaded, mapTheme, selectedPort]);

  // 5. Moving Commodity Transport Lines Animation
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded.routes || routes.length === 0 || !layers.routes) return;

    const activeRoutes = selectedPort === "ALL"
      ? routes
      : routes.filter((r) => getIndiaPortCode(r.dest_lat, r.dest_long) === selectedPort);

    const animatedTracks = activeRoutes.map((r, idx) => {
      const path = greatCircle([r.origin_long, r.origin_lat], [r.dest_long, r.dest_lat], 50);
      const color = r.risk_score >= 80 ? "#ef4444" : r.risk_score >= 60 ? "#f97316" : r.risk_score >= 35 ? "#eab308" : "#22d3ee";
      const durationMs = 4200 + ((idx * 683) % 5500);
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
      if (now - lastRenderTime >= 24) {
        lastRenderTime = now;
        try {
          if (map.isStyleLoaded() && map.getLayer("route-lines-active")) {
            const source = map.getSource("trade-routes-active") as maplibregl.GeoJSONSource | undefined;
            if (source) {
              const features: GeoJSON.Feature[] = [];
              for (const track of animatedTracks) {
                const N = track.path.length;
                if (N < 4) continue;

                const angle = (2 * Math.PI * (now + track.phaseOffset)) / track.durationMs;
                const progress = 0.5 * (1 - Math.cos(angle));

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
        } catch (err) {
          // handled during unmount
        }
      }
      animId = requestAnimationFrame(animateLines);
    };

    animId = requestAnimationFrame(animateLines);
    return () => {
      cancelAnimationFrame(animId);
    };
  }, [routes, loaded.routes, layers.routes, selectedPort]);

  // 6. Boundaries and Country fills
  useEffect(() => {
    const map = mapRef.current;
    if (!map || boundariesData.length === 0) return;

    const features = boundariesData
      .filter((b) => b.geojson)
      .map((b) => {
        const gj = b.geojson as { properties?: Record<string, unknown> };
        const cii = ciiScores.get(b.iso_a3);
        return {
          ...gj,
          properties: {
            ...(gj.properties ?? {}),
            iso_a3: b.iso_a3,
            __cii: cii === undefined ? -1 : cii,
          },
        };
      });

    const addBoundaries = () => {
      if (!map || !map.isStyleLoaded()) return;

      try {
        if (!map.getSource("countries")) {
          map.addSource("countries", {
            type: "geojson",
            data: { type: "FeatureCollection", features } as never,
          });
          map.addLayer({
            id: "cii-fill",
            type: "fill",
            source: "countries",
            paint: {
              "fill-color": [
                "case",
                ["<=", ["get", "__cii"], 0],
                "transparent",
                [
                  "interpolate",
                  ["linear"],
                  ["get", "__cii"],
                  10,
                  "rgba(58,21,32,0.3)",
                  30,
                  "rgba(138,26,26,0.45)",
                  50,
                  "rgba(194,37,37,0.55)",
                  70,
                  "rgba(255,64,48,0.65)",
                  90,
                  "rgba(255,122,92,0.75)",
                ],
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

          map.on("mousemove", "cii-fill", (e) => {
            const f = e.features?.[0];
            if (!f) return;
            map.getCanvas().style.cursor = "crosshair";
            const code = f.properties?.iso_a3 as string;
            const score = ciiScores.get(code);
            showPopup(
              map,
              e.lngLat,
              `<div class="wm-pop"><span class="wm-pop-code">${code}</span><br/>CII <b>${
                score !== undefined ? score.toFixed(1) : "—"
              }</b>/100</div>`
            );
          });
          map.on("mouseleave", "cii-fill", () => {
            map.getCanvas().style.cursor = "";
          });
        } else {
          (map.getSource("countries") as maplibregl.GeoJSONSource).setData({
            type: "FeatureCollection",
            features,
          } as never);
        }
      } catch (err) {
        console.warn("Boundaries layer error:", err);
      }
    };

    if (map.isStyleLoaded()) {
      addBoundaries();
    } else {
      map.once("load", addBoundaries);
    }
  }, [boundariesData, ciiScores, mapTheme]);

  return (
    <div className="map-zone">
      <div id="globe" ref={mapContainerRef} />
      <div className="globe-atmosphere-glow" />

      <div className="map-overlays">
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
            <input type="checkbox" checked={layers.naval} onChange={() => toggleLayer("naval")} />
            <span className="checkmark" />
            WARSHIPS & FLEETS ({navalFleets.length})
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
          <span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#00e5ff" style={{ verticalAlign: "-2px", marginRight: "2px" }}>
              <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
            </svg>
            Mil Flight
          </span>
          <span>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#38bdf8" style={{ verticalAlign: "-2px", marginRight: "2px" }}>
              <path d="M20 21c-1.39 0-2.78-.47-4-1.32-2.44 1.71-5.56 1.71-8 0C6.78 20.53 5.39 21 4 21H2v2h2c1.38 0 2.74-.35 4-.99 2.52 1.29 5.48 1.29 8 0 1.26.65 2.62.99 4 .99h2v-2h-2zM3.95 19H4c1.6 0 3.02-.88 4-2 .98 1.12 2.4 2 4 2s3.02-.88 4-2c.98 1.12 2.4 2 4 2h.05l1.89-6.68c.08-.26.06-.54-.06-.78s-.33-.41-.6-.46L20 11V8c0-.55-.45-1-1-1h-5V4c0-.55-.45-1-1-1h-2c-.55 0-1 .45-1 1v3H5c-.55 0-1 .45-1 1v3l-1.33.28c-.27.05-.48.22-.6.46s-.14.52-.06.78L3.95 19zM6 9h12v2H6V9z" />
            </svg>
            Naval Fleet
          </span>
          <span><i className="dot d-base" /> Base</span>
          <span><i className="dot d-nuc" /> Nuclear</span>
          <span><i className="dot d-space" /> Spaceport</span>
          <span><i className="dot d-quake" /> Quake M4+</span>
          <span><i className="sq sq-red" /> Chokepoint</span>
          <span><i className="line lg-route" /> Trade Route</span>
          <span><i className="line lg-cable" /> Cable</span>
        </div>
      </div>
    </div>
  );
};

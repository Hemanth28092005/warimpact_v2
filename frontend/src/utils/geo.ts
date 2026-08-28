import maplibregl from "maplibre-gl";

export function greatCircle(a: [number, number], b: [number, number], n = 48): [number, number][] {
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

export function calculateBearing(start: [number, number], end: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toDeg = (r: number) => (r * 180) / Math.PI;
  const lon1 = toRad(start[0]), lat1 = toRad(start[1]);
  const lon2 = toRad(end[0]), lat2 = toRad(end[1]);
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

let popup: maplibregl.Popup | null = null;
export function showPopup(map: maplibregl.Map, lngLat: maplibregl.LngLat, html: string) {
  if (popup) popup.remove();
  popup = new maplibregl.Popup({ closeButton: false, closeOnClick: true, offset: 8 })
    .setLngLat(lngLat)
    .setHTML(html)
    .addTo(map);
}

export interface IndianPort {
  code: string;
  name: string;
  state: string;
  lat: number;
  long: number;
  commodities: string;
  trafficType: string;
}

export const INDIAN_PORTS: IndianPort[] = [
  {
    code: "IN-VAD",
    name: "Vadinar / Sikka Port",
    state: "Gujarat",
    lat: 22.4500,
    long: 69.8000,
    commodities: "Crude Oil, Refined Petroleum Exports",
    trafficType: "Major Crude Oil & Petrochemicals Terminal",
  },
  {
    code: "IN-IXY",
    name: "Kandla (Deendayal) Port",
    state: "Gujarat",
    lat: 22.8360,
    long: 70.2185,
    commodities: "Vegetable Oils, Fertilizers, Basmati Rice",
    trafficType: "Major Bulk & Edible Oil Hub",
  },
  {
    code: "IN-MUN",
    name: "Mundra Commercial Port",
    state: "Gujarat",
    lat: 22.7441,
    long: 69.7025,
    commodities: "Petroleum Products, Plastics Raw, Cotton Yarn",
    trafficType: "Largest Multi-Cargo Commercial Port",
  },
  {
    code: "IN-DHJ",
    name: "Dahej Chemical & LNG Port",
    state: "Gujarat",
    lat: 21.7000,
    long: 72.5800,
    commodities: "Organic Chemicals, LNG, Refined Copper",
    trafficType: "PCPIR Chemical Corridor & Petronet LNG",
  },
  {
    code: "IN-HZR",
    name: "Hazira / Surat Port",
    state: "Gujarat",
    lat: 21.1086,
    long: 72.6358,
    commodities: "Diamonds Unworked, Cut Diamonds & Jewelry",
    trafficType: "Global Diamond Hub, LNG & Heavy Engineering",
  },
  {
    code: "IN-BOM",
    name: "Jawaharlal Nehru Port (JNPT)",
    state: "Maharashtra",
    lat: 18.9500,
    long: 72.9500,
    commodities: "Gold Bullion, Machinery Parts, Medical Instruments",
    trafficType: "Premier Container Gateway of India",
  },
  {
    code: "IN-MRM",
    name: "Mormugao Port",
    state: "Goa",
    lat: 15.4167,
    long: 73.8000,
    commodities: "Refined Sugar, Iron Ore & General Cargo",
    trafficType: "Deepwater Natural Harbor",
  },
  {
    code: "IN-COK",
    name: "Cochin Port / Kochi LNG",
    state: "Kerala",
    lat: 9.9656,
    long: 76.2711,
    commodities: "Spices, Seafood & Shrimp, Tea & Coffee, LNG",
    trafficType: "Spice Coast International Transshipment Hub",
  },
  {
    code: "IN-TCR",
    name: "V.O. Chidambaranar (Tuticorin)",
    state: "Tamil Nadu",
    lat: 8.7533,
    long: 78.1633,
    commodities: "Cotton Yarn & Fabrics, Refined Copper",
    trafficType: "All-Weather Southern Industrial Gateway",
  },
  {
    code: "IN-MAA",
    name: "Chennai Port & Kamarajar Ennore",
    state: "Tamil Nadu",
    lat: 13.0844,
    long: 80.2980,
    commodities: "Automobiles Ro-Ro, Telecom Mobiles, ICs, Leather",
    trafficType: "Automotive Hub & Electronic Corridors",
  },
  {
    code: "IN-KID",
    name: "Kakinada Deepwater Port",
    state: "Andhra Pradesh",
    lat: 16.9890,
    long: 82.2874,
    commodities: "Non-Basmati Rice, Agricultural Exports",
    trafficType: "East Coast Agri-Bulk Deepwater Terminal",
  },
  {
    code: "IN-VTZ",
    name: "Visakhapatnam Port",
    state: "Andhra Pradesh",
    lat: 17.6868,
    long: 83.2986,
    commodities: "Coking Coal, Steel Flat, Pharmaceuticals, Frozen Shrimp",
    trafficType: "Major Bulk, Steel & Pharma Port",
  },
  {
    code: "IN-PRT",
    name: "Paradip Port",
    state: "Odisha",
    lat: 20.2644,
    long: 86.6085,
    commodities: "Thermal/Coking Coal, Steel Exports, Fertilizers",
    trafficType: "Major Dry Bulk & Energy Port of East Coast",
  },
  {
    code: "IN-HLD",
    name: "Syama Prasad Mookerjee Port (Haldia/Kolkata)",
    state: "West Bengal",
    lat: 22.0333,
    long: 88.0833,
    commodities: "Darjeeling/Assam Tea, Leather Goods, Vegetable Oils",
    trafficType: "Riverine Multi-Modal Gateway for Eastern India",
  },
];

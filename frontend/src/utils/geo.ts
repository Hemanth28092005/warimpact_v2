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

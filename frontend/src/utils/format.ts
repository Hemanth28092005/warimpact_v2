export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${Math.max(1, m)}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function utcClock(): string {
  const d = new Date();
  const days = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
  const p = (n: number) => String(n).padStart(2, '0');
  return `${days[d.getUTCDay()]}, ${p(d.getUTCDate())} ${['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][d.getUTCMonth()]} ${d.getUTCFullYear()} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
}

export function defcon(avgCii: number | null): number {
  if (avgCii === null) return 5;
  if (avgCii >= 72) return 2;
  if (avgCii >= 58) return 3;
  if (avgCii >= 42) return 4;
  return 5;
}

export function getIndiaPortName(lat: number, lon: number): string {
  if (Math.abs(lat - 22.45) < 0.2 && Math.abs(lon - 69.80) < 0.2) return "Vadinar / Sikka (GJ)";
  if (Math.abs(lat - 21.1086) < 0.2 && Math.abs(lon - 72.6358) < 0.2) return "Surat / Hazira (GJ)";
  if (Math.abs(lat - 22.7441) < 0.2 && Math.abs(lon - 69.7025) < 0.2) return "Mundra Port (GJ)";
  if (Math.abs(lat - 22.8360) < 0.2 && Math.abs(lon - 70.2185) < 0.2) return "Kandla Port (GJ)";
  if (Math.abs(lat - 21.7000) < 0.2 && Math.abs(lon - 72.5800) < 0.2) return "Dahej PCPIR Port (GJ)";
  if (Math.abs(lat - 18.9500) < 0.2 && Math.abs(lon - 72.9500) < 0.2) return "Mumbai JNPT (MH)";
  if (Math.abs(lat - 15.4167) < 0.2 && Math.abs(lon - 73.8000) < 0.2) return "Mormugao Port (GA)";
  if (Math.abs(lat - 9.9656) < 0.2 && Math.abs(lon - 76.2711) < 0.2) return "Kochi Port (KL)";
  if (Math.abs(lat - 8.7533) < 0.2 && Math.abs(lon - 78.1633) < 0.2) return "Tuticorin V.O.C. (TN)";
  if (Math.abs(lat - 13.0844) < 0.2 && Math.abs(lon - 80.2980) < 0.2) return "Chennai / Ennore (TN)";
  if (Math.abs(lat - 16.9890) < 0.2 && Math.abs(lon - 82.2874) < 0.2) return "Kakinada Port (AP)";
  if (Math.abs(lat - 17.6868) < 0.2 && Math.abs(lon - 83.2986) < 0.2) return "Visakhapatnam (AP)";
  if (Math.abs(lat - 20.2644) < 0.2 && Math.abs(lon - 86.6085) < 0.2) return "Paradip Port (OD)";
  if (Math.abs(lat - 22.0333) < 0.2 && Math.abs(lon - 88.0833) < 0.2) return "Haldia / Kolkata (WB)";
  return "Indian Maritime Port";
}
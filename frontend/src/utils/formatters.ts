export function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const s = n > 0 ? `+${n.toFixed(2)}%` : `${n.toFixed(2)}%`;
  return s;
}

export function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 1 });
}

export function defcon(avgCii: number | null): number {
  if (avgCii === null) return 4;
  if (avgCii >= 75) return 2;
  if (avgCii >= 58) return 3;
  if (avgCii >= 42) return 4;
  return 5;
}

export function timeAgo(dateStr: string): string {
  try {
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return dateStr;
  }
}

export function LegendBar() {
  return (
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
  );
}
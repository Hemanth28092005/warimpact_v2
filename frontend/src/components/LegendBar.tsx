export function LegendBar() {
  return (
    <div className="legend-bar">
      <span className="lg-title">LEGEND</span>
      <span><i className="dot d-high" /> Alert</span>
      <span><i className="dot d-flight" /> Mil Flight</span>
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
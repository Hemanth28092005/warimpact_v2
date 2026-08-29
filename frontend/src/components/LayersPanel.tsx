import { useUIStore } from '../store';

export function LayersPanel() {
  const { layers, toggleLayer } = useUIStore();

  const layerConfig = [
    { key: 'cii' as const, label: 'CONFLICT (CII)' },
    { key: 'flights' as const, label: 'MILITARY FLIGHTS' },
    { key: 'naval' as const, label: 'WARSHIPS & FLEETS' },
    { key: 'bases' as const, label: 'MILITARY BASES' },
    { key: 'nuclear' as const, label: 'NUCLEAR SITES' },
    { key: 'spaceports' as const, label: 'SPACEPORTS' },
    { key: 'cables' as const, label: 'CABLES & PIPES' },
    { key: 'routes' as const, label: 'TRADE ROUTES' },
    { key: 'quakes' as const, label: 'SEISMIC EVENTS' },
    { key: 'chokes' as const, label: 'CHOKEPOINTS' },
    { key: 'protests' as const, label: 'CIVIL UNREST' },
  ] as const;

  return (
    <div className="layers-panel">
      <div className="layers-head">
        <span>INTEL LAYERS</span>
        <span className="layers-q">11</span>
      </div>
      {layerConfig.map(({ key, label }) => (
        <label key={key} className="layer-row">
          <input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} />
          <span className="checkmark" />
          {label}
        </label>
      ))}
      <div className="layers-src">@ ESRI SATELLITE · ADSB.LOL · GDELT · USGS</div>
    </div>
  );
}
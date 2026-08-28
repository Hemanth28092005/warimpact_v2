import { useUIStore } from '../store';
import { TV_CHANNELS } from '../types';

export function TVPanel() {
  const { showTv, setShowTv, tvChannel, setTvChannel, tvMinimized, setTvMinimized } = useUIStore();

  if (!showTv) return null;

  const channel = TV_CHANNELS.find((c) => c.id === tvChannel);

  return (
    <div className={`tv-panel ${tvMinimized ? 'minimized' : ''}`}>
      <div className="tv-header">
        <div className="tv-title">
          <span className="tv-rec-dot" />
          <span>LIVE NEWS BROADCAST</span>
        </div>
        <div className="tv-controls">
          <button className="tv-ctrl-btn" onClick={() => setTvMinimized(!tvMinimized)}>{tvMinimized ? '▢' : '—'}</button>
          <button className="tv-ctrl-btn" onClick={() => setShowTv(false)}>✕</button>
        </div>
      </div>

      {!tvMinimized && (
        <>
          <div className="tv-channels">
            {TV_CHANNELS.map((ch) => (
              <button key={ch.id} className={`tv-chan-btn ${tvChannel === ch.id ? 'active' : ''}`} onClick={() => setTvChannel(ch.id)}>
                {ch.name}
              </button>
            ))}
          </div>
          <div className="tv-body">
            {channel && (
              <iframe
                className="tv-iframe"
                src={channel.url}
                title="Live News Stream"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            )}
          </div>
          <div className="tv-footer"><span>UNMUTE IN PLAYER FOR AUDIO · LOW-LATENCY EMBED</span></div>
        </>
      )}
    </div>
  );
}
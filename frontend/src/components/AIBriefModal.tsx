import React from "react";
import { WorldBrief } from "../types";

interface AIBriefModalProps {
  showBrief: boolean;
  onClose: () => void;
  briefData: WorldBrief | null | undefined;
  briefLoading: boolean;
  briefError: string | null;
  onRefresh: () => void;
}

export const AIBriefModal: React.FC<AIBriefModalProps> = ({
  showBrief,
  onClose,
  briefData,
  briefLoading,
  briefError,
  onRefresh,
}) => {
  if (!showBrief) return null;

  return (
    <div className="brief-modal-overlay" onClick={onClose}>
      <div className="brief-modal" onClick={(e) => e.stopPropagation()}>
        <div className="brief-header">
          <div className="brief-title-block">
            <span className="brief-badge">AI SYNTHESIS</span>
            <span className="brief-title">GLOBAL SITUATION BRIEF</span>
          </div>
          <div className="brief-actions">
            <button
              className="brief-btn-refresh"
              onClick={onRefresh}
              disabled={briefLoading}
            >
              {briefLoading ? "ANALYZING..." : "⟳ REFRESH BRIEF"}
            </button>
            <button className="brief-btn-close" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        <div className="brief-content">
          {briefLoading && (
            <div className="brief-loading">
              <span className="spinner" />
              <span>SYNTHESIZING CROSS-DOMAIN GEOPOLITICAL SIGNALS VIA GROQ LLM...</span>
            </div>
          )}

          {briefError && !briefLoading && (
            <div className="brief-err">
              <b>Failed to generate situation brief:</b> {briefError}
            </div>
          )}

          {briefData && !briefLoading && (
            <>
              <div className="brief-quote-box">
                <div className="brief-quote-bar" />
                <div className="brief-quote-text">{briefData.brief}</div>
              </div>

              <div className="brief-signals-heading">
                TELEMETRY INPUTS & CORROBORATING SIGNALS
              </div>

              <div className="brief-signals-grid">
                <div className="signal-card">
                  <span className="sig-label">TOP INSTABILITY (CII)</span>
                  <div className="sig-tags">
                    {briefData.signals?.top_cii?.map(([code, score]) => (
                      <span key={code} className="sig-tag crit">
                        {code}: {Number(score).toFixed(1)}
                      </span>
                    )) ?? <span>No active signals</span>}
                  </div>
                </div>
                <div className="signal-card">
                  <span className="sig-label">24H GLOBAL EVENTS</span>
                  <span className="sig-val">{briefData.signals?.events_24h ?? 0}</span>
                </div>
                <div className="signal-card">
                  <span className="sig-label">ELEVATED CHOKEPOINTS</span>
                  <span className="sig-val hot">{briefData.signals?.hot_chokepoints ?? 0}</span>
                </div>
              </div>

              <div className="brief-footer">
                <span>
                  MODEL: <b>{briefData.model}</b>
                </span>
                <span>
                  GENERATED: {new Date(briefData.generated_at).toLocaleString()}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

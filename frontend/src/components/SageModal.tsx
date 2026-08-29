import React, { useEffect, useRef, useState } from 'react';
import { useUIStore } from '../store';
import { sendSageMessage, useSageContext, useSageSuggestions } from '../hooks/useApi';
import type { SageChatMessage, SageTelemetryHighlight } from '../types';

interface MessageItem extends SageChatMessage {
  timestamp: number;
  telemetryHighlights?: SageTelemetryHighlight[];
  followups?: string[];
  modelUsed?: string;
  latencyMs?: number;
}

function renderBoldText(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style={{ color: '#86efac' }}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

function formatReplyContent(rawText: string): JSX.Element[] {
  const lines = rawText.split('\n');
  const elements: JSX.Element[] = [];
  let tableBuffer: string[] = [];

  const flushTable = () => {
    if (tableBuffer.length === 0) return;
    const headerRow = tableBuffer[0];
    const dataRows = tableBuffer.slice(2); // Skip separator row
    const headers = headerRow.split('|').map((s) => s.trim()).filter(Boolean);

    elements.push(
      <div key={`table-${elements.length}`} className="sage-table-wrapper">
        <table className="sage-markdown-table">
          <thead>
            <tr>
              {headers.map((h, hi) => (
                <th key={hi}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((r, ri) => {
              const cells = r.split('|').map((s) => s.trim()).filter(Boolean);
              return (
                <tr key={ri}>
                  {cells.map((c, ci) => (
                    <td key={ci}>{renderBoldText(c)}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
    tableBuffer = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Table detection
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      tableBuffer.push(trimmed);
      continue;
    } else if (tableBuffer.length > 0) {
      flushTable();
    }

    // Headers
    if (trimmed.startsWith('#### ')) {
      elements.push(
        <div key={i} className="sage-msg-h4">
          {trimmed.slice(5)}
        </div>
      );
    } else if (trimmed.startsWith('### ')) {
      elements.push(
        <div key={i} className="sage-msg-h3">
          {trimmed.slice(4)}
        </div>
      );
    } else if (trimmed.startsWith('## ')) {
      elements.push(
        <div key={i} className="sage-msg-h2">
          {trimmed.slice(3)}
        </div>
      );
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ') || trimmed.startsWith('• ')) {
      const content = trimmed.replace(/^[-*•]\s+/, '');
      elements.push(
        <div key={i} className="sage-msg-bullet">
          <span className="sage-bullet-dot">▸</span>
          <div className="sage-bullet-text">{renderBoldText(content)}</div>
        </div>
      );
    } else if (/^\d+\.\s+/.test(trimmed)) {
      const match = trimmed.match(/^(\d+)\.\s+(.*)$/);
      const num = match ? match[1] : '1';
      const content = match ? match[2] : trimmed;
      elements.push(
        <div key={i} className="sage-msg-num-item">
          <span className="sage-num-badge">{num}</span>
          <div className="sage-num-text">{renderBoldText(content)}</div>
        </div>
      );
    } else if (trimmed === '') {
      elements.push(<div key={i} className="sage-msg-spacer" />);
    } else {
      elements.push(
        <div key={i} className="sage-msg-line">
          {renderBoldText(trimmed)}
        </div>
      );
    }
  }

  if (tableBuffer.length > 0) {
    flushTable();
  }

  return elements;
}

export function SageModal(): JSX.Element | null {
  const {
    showSage,
    setShowSage,
    sageMinimized,
    setSageMinimized,
    sageDraftPrompt,
  } = useUIStore();

  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: suggestions = [] } = useSageSuggestions(showSage);
  const { data: contextData } = useSageContext(showSage);

  const loadingSteps = [
    'Connecting to live platform telemetry & DEFCON feeds...',
    'Evaluating maritime corridors & bilateral aggression vectors...',
    'Synthesizing strategic advisory via NVIDIA Nemotron 70B...',
  ];

  // Auto-scroll on new messages or loading state
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading, loadingStep]);

  // Loading animation cycle
  useEffect(() => {
    if (!loading) return;
    setLoadingStep(0);
    const interval = setInterval(() => {
      setLoadingStep((s) => (s + 1) % loadingSteps.length);
    }, 1500);
    return () => clearInterval(interval);
  }, [loading]);

  // Auto-fill prompt if triggered from elsewhere
  useEffect(() => {
    if (sageDraftPrompt && showSage) {
      setInput(sageDraftPrompt);
    }
  }, [sageDraftPrompt, showSage]);

  const handleSend = async (userPromptText?: string) => {
    const promptToSend = (userPromptText || input).trim();
    if (!promptToSend || loading) return;

    setError(null);
    setInput('');

    const userMessage: MessageItem = {
      role: 'user',
      content: promptToSend,
      timestamp: Date.now(),
    };

    const nextHistory = [...messages, userMessage];
    setMessages(nextHistory);
    setLoading(true);

    try {
      const chatHistory = nextHistory.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await sendSageMessage({
        message: promptToSend,
        history: chatHistory,
      });

      const assistantMessage: MessageItem = {
        role: 'assistant',
        content: res.reply,
        timestamp: Date.now(),
        telemetryHighlights: res.telemetry_highlights,
        followups: res.suggested_followups,
        modelUsed: res.model_used,
        latencyMs: res.latency_ms,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Sage advisory engine is temporarily unreachable.';
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  if (!showSage) return null;

  const filteredCategories =
    activeCategory === 'All'
      ? suggestions
      : suggestions.filter((c) => c.category === activeCategory);

  const defconVal = contextData?.defcon_level ? Number(contextData.defcon_level) : null;
  const avgCiiVal = contextData?.global_avg_cii ? Number(contextData.global_avg_cii) : null;
  const volatileList = Array.isArray(contextData?.top_volatile_countries)
    ? (contextData.top_volatile_countries as Array<{ country_code: string; cii_score: number }>)
    : [];

  return (
    <div className="sage-overlay" onClick={() => setShowSage(false)}>
      <div
        className={`sage-panel ${sageMinimized ? 'sage-panel-minimized' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sage-header">
          <div className="sage-header-left">
            <span className="sage-status-dot" />
            <div className="sage-title-stack">
              <span className="sage-title-main">S.A.G.E AI • STRATEGIC ADVISORY</span>
              <span className="sage-title-sub">STRATEGIC ADVISORY & GEOPOLITICAL EVALUATION • NEMOTRON 70B</span>
            </div>
            {defconVal && (
              <span className={`sage-defcon-badge dc-${defconVal}`}>DEFCON {defconVal}</span>
            )}
          </div>
          <div className="sage-header-actions">
            <button
              className="sage-icon-btn"
              title="Clear Conversation"
              onClick={() => {
                if (window.confirm('Clear conversation history with Sage?')) {
                  setMessages([]);
                }
              }}
            >
              ⟲
            </button>
            <button
              className="sage-icon-btn"
              title={sageMinimized ? 'Expand Modal' : 'Minimize Modal'}
              onClick={() => setSageMinimized(!sageMinimized)}
            >
              {sageMinimized ? '▢' : '—'}
            </button>
            <button
              className="sage-icon-btn sage-close-btn"
              title="Close Sage"
              onClick={() => setShowSage(false)}
            >
              ✕
            </button>
          </div>
        </div>

        {!sageMinimized && (
          <>
            {/* Real-time Telemetry Status Banner */}
            <div className="sage-telemetry-banner">
              <div className="sage-telemetry-item">
                <span className="sage-telemetry-label">GLOBAL DEFCON:</span>
                <span className="sage-telemetry-val highlight">{defconVal ? `DEFCON ${defconVal}` : 'DEFCON 3'}</span>
              </div>
              {avgCiiVal !== null && (
                <div className="sage-telemetry-item">
                  <span className="sage-telemetry-label">AVG CII:</span>
                  <span className="sage-telemetry-val">{avgCiiVal.toFixed(1)}/100</span>
                </div>
              )}
              {volatileList.length > 0 && (
                <div className="sage-telemetry-item">
                  <span className="sage-telemetry-label">TOP VOLATILITY:</span>
                  <span className="sage-telemetry-val alert-red">
                    {volatileList[0].country_code} ({volatileList[0].cii_score.toFixed(0)})
                  </span>
                </div>
              )}
              <div className="sage-telemetry-item right">
                <span className="sage-live-pulse" />
                <span className="sage-telemetry-label">LIVE DATA GROUNDED</span>
              </div>
            </div>

            {/* Chat Messages Stream */}
            <div className="sage-chat-stream" ref={scrollRef}>
              {messages.length === 0 && (
                <div className="sage-welcome-hero">
                  <div className="sage-welcome-icon">🌐</div>
                  <div className="sage-welcome-title">Strategic Geopolitical Intelligence & Advisory</div>
                  <div className="sage-welcome-desc">
                    Ask Sage questions about active conflict escalations, maritime chokepoint closures,
                    commodity and energy supply routes, or request tailored risk mitigation strategies.
                  </div>

                  {/* Suggestion Category Filter */}
                  <div className="sage-category-filter">
                    <button
                      className={`sage-cat-tab ${activeCategory === 'All' ? 'active' : ''}`}
                      onClick={() => setActiveCategory('All')}
                    >
                      ✦ ALL DOMAINS
                    </button>
                    {suggestions.map((c) => (
                      <button
                        key={c.category}
                        className={`sage-cat-tab ${activeCategory === c.category ? 'active' : ''}`}
                        onClick={() => setActiveCategory(c.category)}
                      >
                        {c.emoji} {c.category.toUpperCase()}
                      </button>
                    ))}
                  </div>

                  {/* Suggestion Chips */}
                  <div className="sage-suggestions-grid">
                    {filteredCategories.map((cat) => (
                      <div key={cat.category} className="sage-suggestion-group">
                        <div className="sage-group-label">
                          {cat.emoji} {cat.category}
                        </div>
                        <div className="sage-chips-wrap">
                          {cat.prompts.map((p) => (
                            <button
                              key={p}
                              className="sage-prompt-chip"
                              onClick={() => handleSend(p)}
                            >
                              <span className="sage-chip-arrow">›</span>
                              <span>{p}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Message Bubbles */}
              {messages.map((m, idx) => (
                <div key={idx} className={`sage-bubble sage-bubble-${m.role}`}>
                  <div className="sage-bubble-header">
                    <span className="sage-sender-name">
                      {m.role === 'user' ? '👤 OPERATOR' : '🤖 S.A.G.E ADVISOR'}
                    </span>
                    <span className="sage-time">
                      {new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                    {m.latencyMs && (
                      <span className="sage-latency">{m.latencyMs}ms</span>
                    )}
                    {m.modelUsed && (
                      <span className="sage-model-tag">{m.modelUsed}</span>
                    )}
                    {m.role === 'assistant' && (
                      <button
                        className="sage-copy-btn"
                        title="Copy text to clipboard"
                        onClick={() => {
                          navigator.clipboard.writeText(m.content);
                          alert('Sage briefing copied to clipboard.');
                        }}
                      >
                        📋 COPY
                      </button>
                    )}
                  </div>

                  <div className="sage-bubble-body">
                    {formatReplyContent(m.content)}
                  </div>

                  {/* Telemetry Highlights */}
                  {m.telemetryHighlights && m.telemetryHighlights.length > 0 && (
                    <div className="sage-telemetry-tags-row">
                      <span className="sage-tags-title">TELEMETRY REFERENCED:</span>
                      {m.telemetryHighlights.map((h, hi) => (
                        <span key={hi} className="sage-telemetry-pill">
                          <b>{h.label}:</b> {h.value}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Dynamic Follow-up Suggestions */}
                  {m.followups && m.followups.length > 0 && (
                    <div className="sage-followups-row">
                      <span className="sage-followup-title">STRATEGIC DRILL-DOWNS:</span>
                      <div className="sage-followup-chips">
                        {m.followups.map((f, fi) => (
                          <button
                            key={fi}
                            className="sage-followup-chip"
                            onClick={() => handleSend(f)}
                          >
                            ↳ {f}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Loading Indicator */}
              {loading && (
                <div className="sage-bubble sage-bubble-assistant sage-loading-card">
                  <div className="sage-loading-spinner" />
                  <div className="sage-loading-text-stack">
                    <span className="sage-loading-step-title">{loadingSteps[loadingStep]}</span>
                    <span className="sage-loading-step-sub">Cross-domain telemetry alignment in progress</span>
                  </div>
                </div>
              )}

              {/* Error Message */}
              {error && (
                <div className="sage-error-card">
                  <span className="sage-error-icon">⚠</span>
                  <div className="sage-error-content">
                    <b>Intelligence Pipeline Exception:</b> {error}
                  </div>
                </div>
              )}
            </div>

            {/* Input Row */}
            <div className="sage-input-box">
              <textarea
                className="sage-textarea"
                placeholder="Ask Sage about geopolitical risks, chokepoint closures, trade routes, or strategic advice... (Press Enter to send, Shift+Enter for newline)"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                rows={2}
                disabled={loading}
              />
              <button
                className="sage-submit-btn"
                disabled={loading || !input.trim()}
                onClick={() => handleSend()}
                title="Send message to Sage"
              >
                {loading ? '...' : 'TRANSMIT ➤'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default SageModal;

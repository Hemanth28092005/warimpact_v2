import React, { useEffect } from 'react';
import { useUIStore } from '../store';
import { useVoiceConversation } from '../hooks/useVoiceConversation';
import type { SageChatMessage } from '../types';

interface SageVoiceModeProps {
  initialHistory?: SageChatMessage[];
  onHistoryUpdate?: (history: SageChatMessage[]) => void;
  onSwitchToText?: () => void;
  onClose?: () => void;
}

export const SageVoiceMode: React.FC<SageVoiceModeProps> = ({
  initialHistory = [],
  onHistoryUpdate,
  onSwitchToText,
  onClose,
}) => {
  const {
    sageTranscriptOpen,
    setSageTranscriptOpen,
    setSageVoiceMode,
  } = useUIStore();

  const {
    status,
    isListening,
    isThinking,
    isSpeaking,
    isMuted,
    errorMsg,
    interimText,
    audioLevel,
    transcript,
    isSpeechRecognitionSupported,
    toggleListening,
    stopSpeaking,
    toggleMute,
    clearTranscript,
  } = useVoiceConversation({
    initialHistory,
    onHistoryUpdate,
  });

  // Handle Spacebar hotkey to toggle push-to-talk
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if typing in an input
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) return;
      if (e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        toggleListening();
      } else if (e.code === 'Escape') {
        if (sageTranscriptOpen) {
          setSageTranscriptOpen(false);
        } else if (onClose) {
          onClose();
        } else {
          setSageVoiceMode(false);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleListening, sageTranscriptOpen, setSageTranscriptOpen, onClose, setSageVoiceMode]);

  const handleExit = () => {
    stopSpeaking();
    setSageVoiceMode(false);
    if (onClose) onClose();
  };

  const handleTextSwitch = () => {
    stopSpeaking();
    setSageVoiceMode(false);
    if (onSwitchToText) onSwitchToText();
  };

  // Generate 24 audio visualizer waveform bars
  const barsCount = 24;
  const bars = Array.from({ length: barsCount }).map((_, i) => {
    const factor = Math.sin((i / barsCount) * Math.PI);
    const dynamicHeight = isListening || isSpeaking
      ? Math.max(8, Math.min(100, (audioLevel * 140 * factor) + (Math.random() * 8)))
      : isThinking
      ? 14 + Math.sin(Date.now() / 200 + i) * 10
      : 8;
    return dynamicHeight;
  });

  return (
    <div className="sage-voice-overlay">
      <div className="sage-voice-container">
        {/* Top Header */}
        <header className="sage-voice-header">
          <div className="sage-voice-brand">
            <span className="sage-status-dot" />
            <div className="sage-voice-title-stack">
              <span className="sage-voice-title-main">S.A.G.E • VOICE ADVISORY</span>
              <span className="sage-voice-title-sub">KOKORO NEURAL TTS & SPEECH INTELLIGENCE</span>
            </div>
          </div>

          <div className="sage-voice-header-actions">
            <button
              className={`sage-icon-btn ${isMuted ? 'active-mute' : ''}`}
              onClick={toggleMute}
              title={isMuted ? 'Unmute Audio' : 'Mute Sage Audio'}
            >
              {isMuted ? '🔇 MUTED' : '🔊 AUDIO'}
            </button>
            <button
              className="sage-icon-btn"
              onClick={handleTextSwitch}
              title="Switch to Text Mode"
            >
              💬 TEXT MODE
            </button>
            <button
              className="sage-icon-btn sage-close-btn"
              onClick={handleExit}
              title="Close Voice Mode"
            >
              ✕
            </button>
          </div>
        </header>

        {/* Center Stage: Interactive Tactical Orb & Waveform */}
        <main className="sage-voice-main">
          <div className={`sage-orb-wrapper status-${status}`}>
            {/* Pulsing Aura Rings */}
            <div
              className="sage-orb-ring ring-outer"
              style={{
                transform: `scale(${1 + audioLevel * 0.4})`,
                opacity: 0.2 + audioLevel * 0.6,
              }}
            />
            <div
              className="sage-orb-ring ring-mid"
              style={{
                transform: `scale(${1 + audioLevel * 0.25})`,
                opacity: 0.35 + audioLevel * 0.5,
              }}
            />

            {/* Core Neural Orb */}
            <button
              className={`sage-orb-core ${isListening ? 'listening' : ''} ${isSpeaking ? 'speaking' : ''} ${isThinking ? 'thinking' : ''}`}
              onClick={toggleListening}
              title="Tap or Space to Talk"
            >
              <div className="sage-orb-inner-glow" />
              <div className="sage-orb-icon">
                {isListening ? (
                  <span className="mic-active-icon">🎙️</span>
                ) : isThinking ? (
                  <span className="thinking-pulse-icon">⚡</span>
                ) : isSpeaking ? (
                  <span className="speaking-wave-icon">🔊</span>
                ) : (
                  <span className="mic-idle-icon">🎙️</span>
                )}
              </div>
            </button>
          </div>

          {/* Dynamic Audio Visualizer Bars */}
          <div className="sage-voice-bars">
            {bars.map((h, idx) => (
              <div
                key={idx}
                className={`sage-vbar ${status}`}
                style={{ height: `${h}px` }}
              />
            ))}
          </div>

          {/* Status Text & Interim Speech */}
          <div className="sage-voice-status-box">
            <div className={`sage-status-pill status-${status}`}>
              {status === 'listening' && '● LISTENING...'}
              {status === 'thinking' && '✦ SYNTHESIZING INTELLIGENCE...'}
              {status === 'speaking' && '▲ S.A.G.E SPEAKING (KOKORO TTS)'}
              {status === 'idle' && '◆ READY — TAP MIC OR SPACEBAR'}
              {status === 'error' && '✖ CONNECTION DISRUPTION'}
            </div>

            {interimText ? (
              <div className="sage-interim-text">"{interimText}"</div>
            ) : status === 'idle' ? (
              <div className="sage-voice-hint">
                Speak naturally about conflict hotspots, shipping chokepoints, or trade risk.
              </div>
            ) : null}

            {errorMsg && (
              <div className="sage-voice-error-banner">
                ⚠️ {errorMsg}
              </div>
            )}
          </div>
        </main>

        {/* Bottom Controls Bar */}
        <footer className="sage-voice-footer">
          <div className="sage-voice-footer-left">
            <button
              className={`sage-mic-action-btn ${isListening ? 'active-listening' : ''}`}
              onClick={toggleListening}
            >
              {isListening ? '⏹ STOP LISTENING' : '🎙️ TAP TO SPEAK (SPACE)'}
            </button>
            {isSpeaking && (
              <button className="sage-stop-speaking-btn" onClick={stopSpeaking}>
                ⏹ STOP AUDIO
              </button>
            )}
          </div>

          <div className="sage-voice-footer-right">
            <button
              className={`sage-transcript-toggle-btn ${sageTranscriptOpen ? 'active' : ''}`}
              onClick={() => setSageTranscriptOpen(!sageTranscriptOpen)}
            >
              📜 {sageTranscriptOpen ? 'HIDE TRANSCRIPT' : 'SHOW TRANSCRIPT'} ({transcript.length})
            </button>
          </div>
        </footer>

        {/* Slide-out Running Transcript Panel */}
        <aside className={`sage-voice-transcript-drawer ${sageTranscriptOpen ? 'open' : ''}`}>
          <div className="sage-transcript-header">
            <span className="sage-transcript-title">CONVERSATION TRANSCRIPT</span>
            <div className="sage-transcript-actions">
              <button
                className="sage-transcript-clear-btn"
                onClick={clearTranscript}
                title="Clear transcript history"
              >
                ⟲ CLEAR
              </button>
              <button
                className="sage-transcript-close-btn"
                onClick={() => setSageTranscriptOpen(false)}
              >
                ✕
              </button>
            </div>
          </div>

          <div className="sage-transcript-body">
            {transcript.length === 0 ? (
              <div className="sage-transcript-empty">
                // No conversation recorded yet. Tap the microphone and speak.
              </div>
            ) : (
              transcript.map((t) => (
                <div key={t.id} className={`sage-bubble sage-bubble-${t.role}`}>
                  <div className="sage-bubble-header">
                    <span className="sage-sender-name">
                      {t.role === 'user' ? '👤 OPERATOR' : '🤖 S.A.G.E ADVISOR'}
                    </span>
                    <span className="sage-time">
                      {new Date(t.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                    {t.model_used && (
                      <span className="sage-model-tag">{t.model_used}</span>
                    )}
                  </div>
                  <div className="sage-bubble-body">
                    {t.text}
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
};

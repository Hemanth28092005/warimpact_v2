import { useState, useEffect, useRef, useCallback } from 'react';
import type { VoiceConversationStatus, VoiceTurn, SageChatMessage, SageChatRequest } from '../types';
import { sendSageMessage, synthesizeSageSpeech } from './useApi';

// Type definitions for SpeechRecognition API
interface IWindow extends Window {
  SpeechRecognition?: any;
  webkitSpeechRecognition?: any;
}

export interface UseVoiceConversationProps {
  initialHistory?: SageChatMessage[];
  onHistoryUpdate?: (history: SageChatMessage[]) => void;
}

export function useVoiceConversation({ initialHistory = [], onHistoryUpdate }: UseVoiceConversationProps = {}) {
  const [status, setStatus] = useState<VoiceConversationStatus>('idle');
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [interimText, setInterimText] = useState<string>('');
  const [audioLevel, setAudioLevel] = useState<number>(0); // 0.0 - 1.0 for visualizer
  const [transcript, setTranscript] = useState<VoiceTurn[]>(() =>
    initialHistory.map((m, i) => ({
      id: `init-${i}`,
      role: m.role as 'user' | 'assistant',
      text: m.content,
      timestamp: Date.now() - (initialHistory.length - i) * 30000,
    }))
  );

  const recognitionRef = useRef<any>(null);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const isSpeechRecognitionSupported = typeof window !== 'undefined' &&
    !!((window as IWindow).SpeechRecognition || (window as IWindow).webkitSpeechRecognition);

  // Sync transcript changes back to parent
  const runningMessagesRef = useRef<SageChatMessage[]>(initialHistory);
  useEffect(() => {
    runningMessagesRef.current = transcript.map((t) => ({
      role: t.role,
      content: t.text,
    }));
    if (onHistoryUpdate) {
      onHistoryUpdate(runningMessagesRef.current);
    }
  }, [transcript, onHistoryUpdate]);

  // Audio level analyzer loop for mic input & audio output
  const startVisualizer = useCallback((sourceNode: AudioNode) => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    const ctx = audioContextRef.current;
    if (ctx.state === 'suspended') {
      ctx.resume();
    }

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.8;
    sourceNode.connect(analyser);
    analyserRef.current = analyser;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateLevel = () => {
      if (!analyserRef.current) return;
      analyserRef.current.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / (dataArray.length * 255);
      setAudioLevel(Math.min(1.0, avg * 1.6));
      animFrameRef.current = requestAnimationFrame(updateLevel);
    };

    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = requestAnimationFrame(updateLevel);
  }, []);

  const stopVisualizer = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // Stop any active TTS audio or speech synthesis
  const stopSpeaking = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.src = '';
      currentAudioRef.current = null;
    }
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    stopVisualizer();
    setStatus('idle');
  }, [stopVisualizer]);

  // Fallback to browser SpeechSynthesis if Kokoro TTS is unreachable
  const speakWithBrowserFallback = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (typeof window === 'undefined' || !window.speechSynthesis) {
        resolve();
        return;
      }
      window.speechSynthesis.cancel();

      // Strip markdown for clean speech
      const clean = text
        .replace(/```[\s\S]*?```/g, '')
        .replace(/[#*`_>•—|🔴🟢🟡⚓🤖✦📺◍🛡️🛢️🚢🌐⚡⚠️⇄→]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

      const utterance = new SpeechSynthesisUtterance(clean);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.lang = 'en-US';

      // Pick a clean English voice if available
      const voices = window.speechSynthesis.getVoices();
      const engVoice = voices.find((v) => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('David')));
      if (engVoice) {
        utterance.voice = engVoice;
      }

      utterance.onstart = () => {
        setStatus('speaking');
      };
      utterance.onend = () => {
        setStatus('idle');
        resolve();
      };
      utterance.onerror = () => {
        setStatus('idle');
        resolve();
      };

      window.speechSynthesis.speak(utterance);
    });
  }, []);

  // Process user speech text -> send to Sage /chat -> speak with Kokoro TTS
  const handleUserMessage = useCallback(
    async (userText: string) => {
      const cleanPrompt = userText.trim();
      if (!cleanPrompt) {
        setStatus('idle');
        return;
      }

      setErrorMsg(null);
      setInterimText('');
      setStatus('thinking');

      const userTurnId = `user-${Date.now()}`;
      const userTurn: VoiceTurn = {
        id: userTurnId,
        role: 'user',
        text: cleanPrompt,
        timestamp: Date.now(),
      };

      const updatedTranscript = [...transcript, userTurn];
      setTranscript(updatedTranscript);

      try {
        // 1. Call Sage AI Chat endpoint
        const chatPayload: SageChatRequest = {
          message: cleanPrompt,
          history: runningMessagesRef.current.slice(-6),
        };

        const chatResponse = await sendSageMessage(chatPayload);
        const replyText = chatResponse.reply;

        const assistantTurnId = `sage-${Date.now()}`;
        const assistantTurn: VoiceTurn = {
          id: assistantTurnId,
          role: 'assistant',
          text: replyText,
          timestamp: Date.now(),
          model_used: chatResponse.model_used,
          latency_ms: chatResponse.latency_ms,
        };

        setTranscript((prev) => [...prev, assistantTurn]);

        // If muted, skip TTS audio and return to idle
        if (isMuted) {
          setStatus('idle');
          return;
        }

        // 2. Synthesize speech using backend Kokoro TTS
        setStatus('speaking');
        try {
          const audioBlob = await synthesizeSageSpeech(replyText);
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          currentAudioRef.current = audio;

          // Connect audio output to visualizer
          if (!audioContextRef.current) {
            audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
          }
          const ctx = audioContextRef.current;
          if (ctx.state === 'suspended') {
            await ctx.resume();
          }

          try {
            const track = ctx.createMediaElementSource(audio);
            track.connect(ctx.destination);
            startVisualizer(track);
          } catch (e) {
            // Already connected or CORS constraint
          }

          audio.onended = () => {
            stopVisualizer();
            setStatus('idle');
            URL.revokeObjectURL(audioUrl);
          };
          audio.onerror = async () => {
            stopVisualizer();
            console.warn('Kokoro audio playback failed, trying browser speech synthesis fallback...');
            await speakWithBrowserFallback(replyText);
          };

          await audio.play();
        } catch (ttsErr: any) {
          console.warn('Kokoro TTS service call failed, falling back to browser SpeechSynthesis:', ttsErr);
          await speakWithBrowserFallback(replyText);
        }
      } catch (err: any) {
        console.error('Sage Voice conversation error:', err);
        setErrorMsg(err.message || 'Failed to get intelligence briefing from Sage.');
        setStatus('error');
        await speakWithBrowserFallback('I encountered a connection disruption while accessing strategic intelligence.');
      }
    },
    [transcript, isMuted, startVisualizer, stopVisualizer, speakWithBrowserFallback]
  );

  // Initialize and start browser SpeechRecognition
  const startListening = useCallback(async () => {
    stopSpeaking();
    setErrorMsg(null);
    setInterimText('');

    if (!isSpeechRecognitionSupported) {
      const err = 'Voice recognition requires Google Chrome or Microsoft Edge.';
      setErrorMsg(err);
      setStatus('error');
      await speakWithBrowserFallback(err);
      return;
    }

    try {
      // Request mic stream to visualize user speech audio levels
      if (!micStreamRef.current) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        micStreamRef.current = stream;
        if (!audioContextRef.current) {
          audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
        }
        const micSource = audioContextRef.current.createMediaStreamSource(stream);
        startVisualizer(micSource);
      }
    } catch (micErr: any) {
      const err = 'Microphone access denied. Please allow microphone permissions in your browser.';
      setErrorMsg(err);
      setStatus('error');
      await speakWithBrowserFallback(err);
      return;
    }

    const SpeechRecognition = (window as IWindow).SpeechRecognition || (window as IWindow).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    let finalTranscript = '';

    recognition.onstart = () => {
      setStatus('listening');
    };

    recognition.onresult = (event: any) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const item = event.results[i];
        if (item.isFinal) {
          finalTranscript += item[0].transcript;
        } else {
          interim += item[0].transcript;
        }
      }
      setInterimText(finalTranscript || interim);
    };

    recognition.onerror = (event: any) => {
      console.warn('Speech recognition error:', event.error);
      if (event.error === 'no-speech') {
        setStatus('idle');
        stopVisualizer();
      } else if (event.error === 'not-allowed') {
        setErrorMsg('Microphone permission blocked.');
        setStatus('error');
        stopVisualizer();
      } else {
        setErrorMsg(`Speech recognition: ${event.error}`);
        setStatus('idle');
        stopVisualizer();
      }
    };

    recognition.onend = () => {
      stopVisualizer();
      if (finalTranscript.trim()) {
        handleUserMessage(finalTranscript.trim());
      } else {
        setStatus('idle');
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch (e) {
      console.warn('Recognition start exception:', e);
    }
  }, [isSpeechRecognitionSupported, stopSpeaking, startVisualizer, stopVisualizer, handleUserMessage, speakWithBrowserFallback]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {}
    }
    stopVisualizer();
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (status === 'listening') {
      setStatus('idle');
    }
  }, [status, stopVisualizer]);

  const toggleListening = useCallback(() => {
    if (status === 'listening') {
      stopListening();
    } else if (status === 'speaking') {
      stopSpeaking();
      startListening();
    } else if (status === 'idle' || status === 'error') {
      startListening();
    }
  }, [status, startListening, stopListening, stopSpeaking]);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next && status === 'speaking') {
        stopSpeaking();
      }
      return next;
    });
  }, [status, stopSpeaking]);

  const clearTranscript = useCallback(() => {
    stopSpeaking();
    setTranscript([]);
    runningMessagesRef.current = [];
    if (onHistoryUpdate) {
      onHistoryUpdate([]);
    }
  }, [stopSpeaking, onHistoryUpdate]);

  // Clean up all resources on unmount
  useEffect(() => {
    return () => {
      stopSpeaking();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {}
      }
      if (micStreamRef.current) {
        micStreamRef.current.getTracks().forEach((t) => t.stop());
        micStreamRef.current = null;
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, [stopSpeaking]);

  return {
    status,
    isListening: status === 'listening',
    isThinking: status === 'thinking',
    isSpeaking: status === 'speaking',
    isMuted,
    errorMsg,
    interimText,
    audioLevel,
    transcript,
    isSpeechRecognitionSupported,
    startListening,
    stopListening,
    toggleListening,
    stopSpeaking,
    toggleMute,
    clearTranscript,
    sendUserMessage: handleUserMessage,
  };
}

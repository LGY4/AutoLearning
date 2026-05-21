import { useState, useRef, useCallback } from "react";
import { Mic, MicOff } from "lucide-react";

interface Props {
  onResult: (text: string) => void;
  disabled?: boolean;
}

// Extend Window for SpeechRecognition
declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  }
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message: string;
}

function getRecognition(): SpeechRecognition | null {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.continuous = false;
  rec.interimResults = false;
  rec.lang = "zh-CN";
  return rec;
}

export function VoiceInput({ onResult, disabled }: Props) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(true);
  const recRef = useRef<SpeechRecognition | null>(null);

  const startListening = useCallback(() => {
    const rec = getRecognition();
    if (!rec) {
      setSupported(false);
      return;
    }

    rec.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0][0].transcript;
      if (event.results[0].isFinal && transcript.trim()) {
        onResult(transcript.trim());
      }
    };

    rec.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === "not-allowed") {
        setSupported(false);
      }
      setListening(false);
    };

    rec.onend = () => {
      setListening(false);
    };

    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      setSupported(false);
    }
  }, [onResult]);

  const stopListening = useCallback(() => {
    recRef.current?.stop();
    setListening(false);
  }, []);

  if (!supported) return null;

  return (
    <button
      className={`voice-btn ${listening ? "listening" : ""}`}
      type="button"
      onClick={listening ? stopListening : startListening}
      disabled={disabled}
      title={listening ? "停止录音" : "语音输入"}
    >
      {listening ? <Mic size={18} /> : <MicOff size={18} />}
    </button>
  );
}

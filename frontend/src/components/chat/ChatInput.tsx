import { useCallback, useEffect, useRef, useState } from "react";
import { Button, message } from "antd";
import { Send, Square, X, Mic, MicOff } from "lucide-react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: (images?: string[]) => void;
  loading: boolean;
  onStop?: () => void;
  disabled?: boolean;
}

export function ChatInput({ value, onChange, onSend, loading, onStop, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [images, setImages] = useState<string[]>([]);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Auto-resize textarea
  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxH = 200;
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
  }, []);

  useEffect(() => {
    autoResize();
  }, [value, autoResize]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, type: "image" | "video") => {
    const files = e.target.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      if (type === "image") {
        if (!file.type.startsWith("image/")) {
          message.warning("仅支持图片文件");
          continue;
        }
        if (file.size > 10 * 1024 * 1024) {
          message.warning("图片大小不能超过 10MB");
          continue;
        }
        const reader = new FileReader();
        reader.onload = () => {
          setImages((prev) => [...prev, reader.result as string]);
        };
        reader.readAsDataURL(file);
      } else {
        if (!file.type.startsWith("video/")) {
          message.warning("仅支持视频文件");
          continue;
        }
        if (file.size > 20 * 1024 * 1024) {
          message.warning("视频大小不能超过 20MB（更大文件需要服务端上传支持）");
          continue;
        }
        const reader = new FileReader();
        reader.onload = () => {
          setImages((prev) => [...prev, reader.result as string]);
        };
        reader.readAsDataURL(file);
      }
    }
    e.target.value = "";
  };

  const handleSend = () => {
    if (!value.trim() && images.length === 0) return;
    onSend(images.length > 0 ? images : undefined);
    setImages([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const removeImage = (index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  };

  // Expose file refs for PlusMenu triggers
  const openImageUpload = () => fileRef.current?.click();
  const openVideoUpload = () => videoRef.current?.click();

  // Voice input via Web Speech API
  const toggleVoice = useCallback(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      message.warning("当前浏览器不支持语音输入");
      return;
    }
    if (listening && recognitionRef.current) {
      recognitionRef.current.stop();
      setListening(false);
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event: any) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      onChange(value + transcript);
    };
    recognition.onerror = () => { setListening(false); };
    recognition.onend = () => { setListening(false); };
    recognition.start();
    recognitionRef.current = recognition;
    setListening(true);
  }, [listening, value, onChange]);

  // Store refs globally for PlusMenu access
  useEffect(() => {
    (window as any).__chatInputRefs = { openImageUpload, openVideoUpload };
    return () => { delete (window as any).__chatInputRefs; };
  }, []);

  return (
    <>
      {images.length > 0 && (
        <div className="chat-image-preview">
          {images.map((img, i) => (
            <div key={i} className="chat-image-thumb">
              <img src={img} alt={`upload-${i}`} />
              <button className="chat-image-remove" onClick={() => removeImage(i)}>
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: "none" }}
        onChange={(e) => handleFileChange(e, "image")}
      />
      <input
        ref={videoRef}
        type="file"
        accept="video/*"
        multiple
        style={{ display: "none" }}
        onChange={(e) => handleFileChange(e, "video")}
      />
      <textarea
        ref={textareaRef}
        className="chat-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入学习目标、知识点或问题...（Enter 发送，Shift+Enter 换行）"
        disabled={disabled}
        rows={1}
      />
      <Button
        className="voice-button"
        shape="circle"
        onClick={toggleVoice}
        disabled={disabled || loading}
        title={listening ? "停止语音" : "语音输入"}
        style={listening ? { background: "#ef4444", borderColor: "#ef4444", color: "white" } : {}}
      >
        {listening ? <MicOff size={18} /> : <Mic size={18} />}
      </Button>
      {loading && onStop ? (
        <Button className="voice-button" shape="circle" danger onClick={onStop} title="停止输出">
          <Square size={18} />
        </Button>
      ) : (
        <Button className="voice-button" shape="circle" type="primary" onClick={handleSend} loading={loading} disabled={disabled}>
          <Send size={18} />
        </Button>
      )}
    </>
  );
}

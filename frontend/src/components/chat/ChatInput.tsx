import { useRef, useState } from "react";
import { Button, Input, Tag, message } from "antd";
import { Image, Send, Square, X } from "lucide-react";
import { VoiceInput } from "./VoiceInput";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: (images?: string[]) => void;
  loading: boolean;
  onStop?: () => void;
  agentName?: string;
  isSystemAgent?: boolean;
  disabled?: boolean;
}

export function ChatInput({ value, onChange, onSend, loading, onStop, agentName, isSystemAgent, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [images, setImages] = useState<string[]>([]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (const file of Array.from(files)) {
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
    }
    e.target.value = "";
  };

  const handleSend = () => {
    if (!value.trim() && images.length === 0) return;
    onSend(images.length > 0 ? images : undefined);
    setImages([]);
  };

  const removeImage = (index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: "none" }}
        onChange={handleFileChange}
      />
      <Button
        className="chat-image-btn"
        shape="circle"
        onClick={() => fileRef.current?.click()}
        disabled={disabled}
        title="上传图片"
      >
        <Image size={18} />
      </Button>
      <VoiceInput
        onResult={(text) => onChange(value ? `${value} ${text}` : text)}
        disabled={disabled}
      />
      <div className="chat-input-main">
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
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onPressEnter={handleSend}
          placeholder="输入学习目标、知识点或问题..."
          disabled={disabled}
        />
      </div>
      {agentName && <Tag color={isSystemAgent ? "blue" : "green"}>{agentName}</Tag>}
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

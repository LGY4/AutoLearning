import { useState, useCallback } from "react";
import { Button, Input, Tag } from "antd";
import { Search, Send } from "lucide-react";
import { apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";

interface TutorMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  nextStep?: string;
  references?: Array<{ title?: string; source?: string }>;
}

interface SearchResult {
  chunk_id: string;
  title: string;
  content: string;
  subject: string;
  score: number;
  tags: string[];
}

export function TutorPage() {
  const { state } = useAppContext();
  const { user } = state;
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  // Knowledge search
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const data = await apiPost<{ results: SearchResult[] }>("/knowledge/search", {
        query: searchQuery.trim(),
        top_k: 5,
      });
      setSearchResults(data.results ?? []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery]);

  const sendQuestion = async () => {
    if (!input.trim() || !user) return;

    const question = input.trim();
    const userMsg: TutorMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const response = await apiPost<{
        conversation_id: string;
        answer: string;
        markdown: string;
        rag_references: Array<Record<string, unknown>>;
        next_step: string;
      }>("/tutor/chat", {
        user_id: user.id,
        question,
        conversation_id: conversationId,
      });

      setConversationId(response.conversation_id);

      const assistantMsg: TutorMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.markdown || response.answer,
        nextStep: response.next_step,
        references: response.rag_references?.map((r) => ({
          title: String(r.title ?? ""),
          source: String(r.source ?? ""),
        })),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errMsg: TutorMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `请求失败：${err instanceof Error ? err.message : "未知错误"}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tutor-page">
      <div className="tutor-search-panel">
        <div className="tutor-search-bar">
          <Search size={16} />
          <input
            className="tutor-search-input"
            placeholder="知识检索 (RAG)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <button className="tutor-search-btn" onClick={handleSearch} disabled={searchLoading} type="button">
            {searchLoading ? "搜索中..." : "搜索"}
          </button>
        </div>
        {searchResults && (
          <div className="tutor-search-results">
            {searchResults.length === 0 ? (
              <p className="tutor-search-empty">未找到相关知识</p>
            ) : (
              searchResults.map((r) => (
                <div key={r.chunk_id} className="tutor-search-item">
                  <div className="tutor-search-item-title">{r.title}</div>
                  <div className="tutor-search-item-content">{r.content.length > 200 ? r.content.slice(0, 200) + "..." : r.content}</div>
                  <div className="tutor-search-item-meta">
                    {r.subject && <span>{r.subject}</span>}
                    <span>相关度 {Math.round(r.score * 100)}%</span>
                    {r.tags.map((t) => <span key={t}>{t}</span>)}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      <div className="tutor-chat-area">
        <div className="tutor-messages">
          {messages.length === 0 && (
            <div className="tutor-empty">
              <p>向 AI 导师提问，获取针对性的学习辅导。</p>
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`tutor-message ${msg.role}`}>
              <div className="tutor-bubble">
                <div className="tutor-content">{msg.content}</div>
                {msg.nextStep && (
                  <Tag color="blue" className="tutor-next-step">
                    下一步：{msg.nextStep}
                  </Tag>
                )}
                {msg.references && msg.references.length > 0 && (
                  <div className="tutor-references">
                    {msg.references.map((ref, i) => (
                      <span key={i} className="tutor-ref-tag">
                        {ref.title || ref.source || `参考 ${i + 1}`}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="tutor-message assistant">
              <div className="tutor-bubble tutor-loading">正在思考...</div>
            </div>
          )}
        </div>

        <div className="tutor-input-bar">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={sendQuestion}
            placeholder="输入你的问题..."
            disabled={loading}
          />
          <Button shape="circle" type="primary" onClick={sendQuestion} loading={loading} disabled={!user}>
            <Send size={18} />
          </Button>
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback, useRef } from "react";
import { Search, MessageSquare, FileText, GitBranch, BookOpen, CornerDownLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAppContext } from "../../context/AppContext";
import { apiGet } from "../../api/client";

interface SearchResult {
  type: "conversation" | "resource" | "knowledge" | "path";
  id: string;
  title: string;
  subtitle: string;
  icon: typeof Search;
  action: () => void;
}

const EMPTY_TIP = "搜索对话、资源、知识点...";

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { state } = useAppContext();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const search = useCallback((q: string) => {
    setQuery(q);
    if (!q.trim()) { setResults([]); return; }

    const items: SearchResult[] = [];
    const lower = q.toLowerCase();

    // Local: conversations
    state.conversations.forEach((c) => {
      if (c.title.toLowerCase().includes(lower)) {
        items.push({
          type: "conversation",
          id: c.conversation_id,
          title: c.title,
          subtitle: `对话 · ${new Date(c.updated_at).toLocaleDateString()}`,
          icon: MessageSquare,
          action: () => { navigate(`/chat`); setOpen(false); },
        });
      }
    });

    // Local: resources
    state.resources.forEach((r) => {
      if (r.title.toLowerCase().includes(lower)) {
        items.push({
          type: "resource",
          id: r.resource_id,
          title: r.title,
          subtitle: `${r.resource_type} · ${r.knowledge_point || ""}`,
          icon: FileText,
          action: () => { navigate(`/chat`); setOpen(false); },
        });
      }
    });

    // Add knowledge search result (RAG)
    items.push({
      type: "knowledge",
      id: "search-kb",
      title: `在知识库中搜索 "${q}"`,
      subtitle: "RAG 知识检索",
      icon: BookOpen,
      action: () => { navigate(`/chat?topic=${encodeURIComponent(q)}`); setOpen(false); },
    });

    setResults(items.slice(0, 10));
    setSelectedIdx(0);
  }, [state]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIdx((i) => Math.min(i + 1, results.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIdx((i) => Math.max(i - 1, 0)); }
    if (e.key === "Enter" && results[selectedIdx]) {
      results[selectedIdx].action();
    }
  };

  if (!open) return null;

  const TYPE_ICONS: Record<string, string> = {
    conversation: "💬",
    resource: "📄",
    knowledge: "🧠",
    path: "🗺️",
  };

  return (
    <div className="search-overlay" onClick={() => setOpen(false)}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <div className="search-input-wrap">
          <Search size={18} className="search-input-icon" />
          <input
            ref={inputRef}
            className="search-input"
            placeholder={EMPTY_TIP}
            value={query}
            onChange={(e) => search(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <kbd className="search-kbd">Esc</kbd>
        </div>
        {results.length > 0 && (
          <div className="search-results">
            {results.map((r, i) => {
              const Icon = r.icon;
              return (
                <button
                  key={`${r.type}-${r.id}`}
                  className={`search-result-item ${i === selectedIdx ? "selected" : ""}`}
                  onClick={r.action}
                  type="button"
                >
                  <div className="search-result-icon">
                    <Icon size={16} />
                  </div>
                  <div className="search-result-text">
                    <span className="search-result-title">{r.title}</span>
                    <span className="search-result-subtitle">{r.subtitle}</span>
                  </div>
                  <span className="search-result-type">{TYPE_ICONS[r.type]}</span>
                </button>
              );
            })}
          </div>
        )}
        {query && results.length === 0 && (
          <div className="search-empty">未找到结果</div>
        )}
        <div className="search-footer">
          <span><kbd>↑↓</kbd> 导航</span>
          <span><kbd>Enter</kbd> 选择</span>
          <span><kbd>Esc</kbd> 关闭</span>
        </div>
      </div>
    </div>
  );
}

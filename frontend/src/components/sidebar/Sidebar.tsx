import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { Button, message } from "antd";
import { BookOpen, ChevronDown, ChevronRight, Film, GitBranch, GraduationCap, History, Library, LogOut, Map as MapIcon, MoreHorizontal, Pen, PenTool, Pencil, Plus, Trash2, TrendingUp, User, Wand2 } from "lucide-react";
import { ThemeToggle } from "../common/ThemeToggle";
import { useAppContext } from "../../context/AppContext";
import { apiPatch, apiDelete, clearAccessToken } from "../../api/client";
import type { ConversationSession } from "../../types/baseline";

interface Props {
  onAuth: () => void;
  onNewSession: () => void;
  onLoadHistory: () => void;
  onLoadConversation: (id: string, conversationType?: string) => void;
  onNavigate?: (path: string) => void;
  onSendMessage?: (message: string) => void;
  activePath?: string;
  mobileOpen?: boolean;
}

// When on /chat, clicking these items sends a chat message instead of navigating
const NAV_CHAT_MESSAGES: Record<string, string> = {
  "/practice": "帮我出几道练习题",
  "/map": "展示学习地图",
  "/video-studio": "帮我生成一个教学视频",
  "/media-studio": "帮我生成一个动画",
  "/dashboard": "看看我的学习情况",
  "/resources": "浏览我的资源",
  "/courses": "查看学习目标",
  "/analytics": "看看我的学习分析",
};

// ── Time grouping ────────────────────────────────────────────────────────

function getTimeGroup(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - today.getDay());

  if (d >= today) return "今天";
  if (d >= yesterday) return "昨天";
  if (d >= weekStart) return "本周";
  return "更早";
}

const TIME_ORDER = ["今天", "昨天", "本周", "更早"];

const LEARN_NAV_ITEMS = [
  { path: "/chat", label: "AI 学习助手", icon: GraduationCap },
  { path: "/practice", label: "练习刷题", icon: PenTool },
  { path: "/map", label: "学习地图", icon: MapIcon },
];

const CREATE_NAV_ITEMS = [
  { path: "/video-studio", label: "知识视频", icon: Film },
  { path: "/media-studio", label: "动画 & 图片", icon: Wand2 },
];

const REVIEW_NAV_ITEMS = [
  { path: "/dashboard", label: "学习看板", icon: TrendingUp },
  { path: "/resources", label: "资源 & 题库", icon: Library },
  { path: "/courses", label: "课程 & 目标", icon: BookOpen },
];

// ── Profile grouping ─────────────────────────────────────────────────────

interface ProfileGroup {
  profileId: string;
  profileName: string;
  conversations: ConversationSession[];
}

interface TimeGroup {
  label: string;
  profileGroups: ProfileGroup[];
}

function groupConversations(conversations: ConversationSession[]): TimeGroup[] {
  // Level 1: group by time
  const timeMap = new Map<string, ConversationSession[]>();
  for (const conv of conversations) {
    const key = getTimeGroup(conv.updated_at);
    if (!timeMap.has(key)) timeMap.set(key, []);
    timeMap.get(key)!.push(conv);
  }

  const result: TimeGroup[] = [];
  for (const timeLabel of TIME_ORDER) {
    const convs = timeMap.get(timeLabel);
    if (!convs || convs.length === 0) continue;

    // Level 2: group by profile_id within time group
    const profileMap = new Map<string, ConversationSession[]>();
    for (const conv of convs) {
      const pid = conv.profile_id || "__unclassified__";
      if (!profileMap.has(pid)) profileMap.set(pid, []);
      profileMap.get(pid)!.push(conv);
    }

    // Sort profile groups by ASCII of profile_id
    const sortedProfileIds = [...profileMap.keys()].sort((a, b) => a.localeCompare(b));

    const profileGroups: ProfileGroup[] = sortedProfileIds.map((pid) => {
      const groupConvs = profileMap.get(pid)!;
      // Sort conversations within group by updated_at desc
      groupConvs.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      return {
        profileId: pid,
        profileName: pid === "__unclassified__" ? "未分类" : (groupConvs[0]?.title || "学习画像"),
        conversations: groupConvs,
      };
    });

    result.push({ label: timeLabel, profileGroups });
  }
  return result;
}

// ── Component ────────────────────────────────────────────────────────────

export function Sidebar({ onAuth, onNewSession, onLoadHistory, onLoadConversation, onNavigate, onSendMessage, activePath = "/", mobileOpen }: Props) {

  const handleNavClick = useCallback((path: string) => {
    // If on /chat and there's a chat message for this path, send message instead of navigating
    if (activePath === "/chat" && onSendMessage && NAV_CHAT_MESSAGES[path]) {
      onSendMessage(NAV_CHAT_MESSAGES[path]);
      return;
    }
    onNavigate?.(path);
  }, [activePath, onNavigate, onSendMessage]);
  const { state, dispatch } = useAppContext();
  const { user, conversations, selectedConversationId, baseAgents, selectedBaseAgentId } = state;
  const hasLogin = Boolean(user);

  const [historyExpanded, setHistoryExpanded] = useState(true);
  const [expandedProfiles, setExpandedProfiles] = useState<Set<string>>(new Set());
  const [menuConvId, setMenuConvId] = useState<string | null>(null);
  const [renamingConvId, setRenamingConvId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    if (!menuConvId) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuConvId(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuConvId]);

  const handleRename = useCallback(async (convId: string) => {
    const title = renameValue.trim();
    if (!title) return;
    try {
      await apiPatch(`/conversations/${convId}`, { title });
      dispatch({
        type: "SET_CONVERSATIONS",
        payload: conversationsRef.current.map((c) => c.conversation_id === convId ? { ...c, title } : c),
      });
    } catch {
      message.error("重命名失败");
    }
    setRenamingConvId(null);
    setMenuConvId(null);
  }, [renameValue, dispatch]);

  const handleDelete = useCallback(async (convId: string) => {
    if (!window.confirm("确定删除该对话？删除后不可恢复。")) return;
    try {
      await apiDelete(`/conversations/${convId}`);
      dispatch({
        type: "SET_CONVERSATIONS",
        payload: conversationsRef.current.filter((c) => c.conversation_id !== convId),
      });
      if (selectedConvIdRef.current === convId) {
        dispatch({ type: "SET_SELECTED_CONVERSATION", payload: null });
        dispatch({ type: "SET_ACTIVE_MESSAGES", payload: [] });
      }
    } catch {
      message.error("删除失败");
    }
    setMenuConvId(null);
  }, [dispatch]);

  const [historySearch, setHistorySearch] = useState("");
  const conversationsRef = useRef(conversations);
  conversationsRef.current = conversations;
  const selectedConvIdRef = useRef(selectedConversationId);
  selectedConvIdRef.current = selectedConversationId;
  const timeGroups = useMemo(() => groupConversations(conversations), [conversations]);
  const filteredTimeGroups = useMemo(() => {
    if (!historySearch.trim()) return timeGroups;
    const q = historySearch.toLowerCase();
    return timeGroups
      .map((tg) => ({
        ...tg,
        profileGroups: tg.profileGroups
          .map((pg) => ({
            ...pg,
            conversations: pg.conversations.filter((c) => (c.title || "").toLowerCase().includes(q)),
          }))
          .filter((pg) => pg.conversations.length > 0),
      }))
      .filter((tg) => tg.profileGroups.length > 0);
  }, [timeGroups, historySearch]);

  const toggleProfile = (profileId: string) => {
    setExpandedProfiles((prev) => {
      const next = new Set(prev);
      if (next.has(profileId)) next.delete(profileId);
      else next.add(profileId);
      return next;
    });
  };

  return (
    <aside className={`profile-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="sidebar-head">
        <strong>AutoLearning</strong>
      </div>

      <button className="sidebar-action" type="button" onClick={onNewSession}>
        <Plus size={18} />
        <span>新会话</span>
      </button>

      <div className="sidebar-group">
        <span className="sidebar-group-title">学习</span>
        {LEARN_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              className={`sidebar-action secondary ${activePath === item.path ? "active" : ""}`}
              type="button"
              onClick={() => handleNavClick(item.path)}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <div className="sidebar-group">
        <span className="sidebar-group-title">创作</span>
        {CREATE_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              className={`sidebar-action secondary ${activePath === item.path ? "active" : ""}`}
              type="button"
              onClick={() => handleNavClick(item.path)}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <div className="sidebar-group">
        <span className="sidebar-group-title">回顾</span>
        {REVIEW_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              className={`sidebar-action secondary ${activePath === item.path ? "active" : ""}`}
              type="button"
              onClick={() => handleNavClick(item.path)}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <div className="sidebar-insight-card">
        <span className="sidebar-group-title">当前概览</span>
        <div className="sidebar-insight-grid">
          <div>
            <strong>{conversations.length}</strong>
            <span>会话</span>
          </div>
          <div>
            <strong>{baseAgents.length}</strong>
            <span>智能体</span>
          </div>
        </div>
      </div>

      {/* Collapsible History Section */}
      <div className="sidebar-history">
        <button
          className="sidebar-history-toggle"
          type="button"
          onClick={() => setHistoryExpanded((v) => !v)}
        >
          <History size={16} />
          <span>历史记录</span>
          <span className="sidebar-history-chevron">
            {historyExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </button>

        {historyExpanded && (
          <div className="sidebar-history-content">
            <input
              className="sidebar-history-search"
              placeholder="搜索对话..."
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
            />
            {filteredTimeGroups.length === 0 && (
              <div className="sidebar-history-empty">{historySearch ? "无匹配对话" : "暂无对话记录"}</div>
            )}
            {filteredTimeGroups.map((tg) => (
              <div className="history-time-group" key={tg.label}>
                <span className="history-time-label">{tg.label}</span>
                {tg.profileGroups.map((pg) => (
                  <div className="history-profile-group" key={pg.profileId}>
                    <button
                      className="history-profile-header"
                      type="button"
                      onClick={() => toggleProfile(pg.profileId)}
                    >
                      <User size={12} />
                      <span className="history-profile-name">{pg.profileName}</span>
                      <span className="history-profile-count">{pg.conversations.length}</span>
                    </button>
                    {expandedProfiles.has(pg.profileId) &&
                      pg.conversations.map((conv) => (
                        <div className="history-item-row" key={conv.conversation_id}>
                          {renamingConvId === conv.conversation_id ? (
                            <form
                              className="history-item-rename"
                              onSubmit={(e) => { e.preventDefault(); handleRename(conv.conversation_id); }}
                            >
                              <input
                                autoFocus
                                value={renameValue}
                                onChange={(e) => setRenameValue(e.target.value)}
                                onBlur={() => { setRenamingConvId(null); setMenuConvId(null); }}
                                onKeyDown={(e) => { if (e.key === "Escape") { setRenamingConvId(null); setMenuConvId(null); } }}
                              />
                            </form>
                          ) : (
                            <button
                              className={`history-item ${conv.conversation_id === selectedConversationId ? "active" : ""}`}
                              type="button"
                              onClick={() => onLoadConversation(conv.conversation_id, conv.conversation_type)}
                            >
                              {conv.conversation_type === "tutor" && <GraduationCap size={12} className="history-item-type-icon" />}
                              <em>{conv.title}</em>
                            </button>
                          )}
                          <button
                            className="history-item-menu-btn"
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setMenuConvId(menuConvId === conv.conversation_id ? null : conv.conversation_id); }}
                            title="更多操作"
                          >
                            <MoreHorizontal size={14} />
                          </button>
                          {menuConvId === conv.conversation_id && (
                            <div className="history-item-menu" ref={menuRef}>
                              <button
                                className="history-item-menu-option"
                                type="button"
                                onClick={() => { setRenamingConvId(conv.conversation_id); setRenameValue(conv.title); setMenuConvId(null); }}
                              >
                                <Pencil size={13} />
                                <span>重命名</span>
                              </button>
                              <button
                                className="history-item-menu-option danger"
                                type="button"
                                onClick={() => handleDelete(conv.conversation_id)}
                              >
                                <Trash2 size={13} />
                                <span>删除</span>
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="sidebar-agent-info">
        <span>{baseAgents.find((a) => a.agent_id === selectedBaseAgentId)?.name ?? "系统默认基座智能体"}</span>
      </div>

      <div className="sidebar-user">
        {hasLogin ? (
          <>
            <div className="sidebar-avatar">{user?.username?.slice(0, 1).toUpperCase() ?? "A"}</div>
            <div className="sidebar-user-info">
              <strong>{user?.username}</strong>
              <div>{user?.role ?? "student"}</div>
            </div>
            <ThemeToggle />
            <button className="sidebar-logout" type="button" onClick={() => { clearAccessToken(); dispatch({ type: "LOGOUT" }); }} title="退出登录">
              <LogOut size={16} />
            </button>
          </>
        ) : (
          <Button className="sidebar-login-btn" onClick={onAuth} icon={<User size={16} />}>
            登录 / 注册
          </Button>
        )}
      </div>
    </aside>
  );
}

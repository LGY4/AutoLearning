import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { Button, message } from "antd";
import { BookOpen, ChevronDown, ChevronRight, Compass, Film, GitBranch, GraduationCap, History, Library, LogOut, Map as MapIcon, MoreHorizontal, Pen, PenTool, Pencil, Plus, Route, Trash2, TrendingUp, User, Wand2, Bell } from "lucide-react";
import { useAppContext } from "../../context/AppContext";
import { apiPatch, apiDelete, clearAccessToken } from "../../api/client";
import { GamificationBar } from "../common/Gamification";
import type { ConversationSession } from "../../types/baseline";

// Simple notification store
const NOTIFS_KEY = "autolearning_notifs";
interface NotifItem { id: string; title: string; desc: string; time: string; read: boolean; }
function loadNotifs(): NotifItem[] { try { return JSON.parse(localStorage.getItem(NOTIFS_KEY) || "[]"); } catch { return []; } }

interface Props {
  onAuth: () => void;
  onNewSession: () => void;
  onLoadHistory: () => void;
  onLoadConversation: (id: string, conversationType?: string) => void;
  onNavigate?: (path: string) => void;
  activePath?: string;
  mobileOpen?: boolean;
}

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

export function Sidebar({ onAuth, onNewSession, onLoadHistory, onLoadConversation, onNavigate, activePath = "/", mobileOpen }: Props) {
  const { state, dispatch } = useAppContext();
  const { user, conversations, selectedConversationId } = state;
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
        payload: conversations.map((c) => c.conversation_id === convId ? { ...c, title } : c),
      });
    } catch {
      message.error("重命名失败");
    }
    setRenamingConvId(null);
    setMenuConvId(null);
  }, [renameValue, conversations, dispatch]);

  const handleDelete = useCallback(async (convId: string) => {
    if (!window.confirm("确定删除该对话？删除后不可恢复。")) return;
    try {
      await apiDelete(`/conversations/${convId}`);
      dispatch({
        type: "SET_CONVERSATIONS",
        payload: conversations.filter((c) => c.conversation_id !== convId),
      });
      if (selectedConversationId === convId) {
        dispatch({ type: "SET_SELECTED_CONVERSATION", payload: null });
        dispatch({ type: "SET_ACTIVE_MESSAGES", payload: [] });
      }
    } catch {
      message.error("删除失败");
    }
    setMenuConvId(null);
  }, [conversations, selectedConversationId, dispatch]);

  const timeGroups = useMemo(() => groupConversations(conversations), [conversations]);

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
        <NotificationBell />
      </div>

      <GamificationBar />

      <button className="sidebar-action" type="button" onClick={onNewSession}>
        <Plus size={18} />
        <span>新对话</span>
      </button>

      <div className="sidebar-nav-section">
      <button
        className={`sidebar-action secondary ${activePath === "/chat" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/chat")}
      >
        <GraduationCap size={18} />
        <span>学习工作区</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/tutor" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/tutor")}
      >
        <GraduationCap size={18} />
        <span>问答辅导</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/video-studio" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/video-studio")}
      >
        <Film size={18} />
        <span>视频工坊</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/media-studio" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/media-studio")}
      >
        <Wand2 size={18} />
        <span>媒体工坊</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/learning-path" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/learning-path")}
      >
        <Route size={18} />
        <span>学习路径</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/map" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/map")}
      >
        <MapIcon size={18} />
        <span>学习地图</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/graphs" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/graphs")}
      >
        <GitBranch size={18} />
        <span>图谱管理</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/practice" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/practice")}
      >
        <PenTool size={18} />
        <span>练习模式</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/dashboard" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/dashboard")}
      >
        <TrendingUp size={18} />
        <span>数据看板</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/courses" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/courses")}
      >
        <BookOpen size={18} />
        <span>课程管理</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/profile-edit" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/profile-edit")}
      >
        <User size={18} />
        <span>学习画像</span>
      </button>

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
            {timeGroups.length === 0 && (
              <div className="sidebar-history-empty">暂无对话记录</div>
            )}
            {timeGroups.map((tg) => (
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

      </div>

      <button
        className={`sidebar-action secondary ${activePath === "/teacher" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/teacher")}
      >
        <TrendingUp size={18} />
        <span>教师看板</span>
      </button>

      <button
        className={`sidebar-action secondary ${activePath === "/resources" ? "active" : ""}`}
        type="button"
        onClick={() => onNavigate?.("/resources")}
      >
        <Library size={18} />
        <span>资源库</span>
      </button>

      <div className="sidebar-user">
        {hasLogin ? (
          <>
            <div className="sidebar-avatar">{user?.username?.slice(0, 1).toUpperCase() ?? "A"}</div>
            <div className="sidebar-user-info">
              <strong>{user?.username}</strong>
              <div>{user?.role ?? "student"}</div>
            </div>
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

function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifs, setNotifs] = useState<NotifItem[]>(loadNotifs);
  const unread = notifs.filter((n) => !n.read).length;

  const markAllRead = () => {
    const updated = notifs.map((n) => ({ ...n, read: true }));
    setNotifs(updated);
    localStorage.setItem(NOTIFS_KEY, JSON.stringify(updated));
  };

  return (
    <div style={{ position: "relative" }}>
      <button className="notif-bell" onClick={() => setOpen(!open)} type="button">
        <Bell size={16} />
        {unread > 0 && <span className="notif-dot" />}
      </button>
      {open && (
        <div className="notif-dropdown" onClick={(e) => e.stopPropagation()}>
          {notifs.length === 0 ? (
            <div className="notif-empty">暂无通知</div>
          ) : (
            <>
              {notifs.slice(0, 20).map((n) => (
                <div key={n.id} className={`notif-item ${n.read ? "" : "unread"}`}>
                  <div className="notif-item-icon">{n.read ? "📌" : "🔔"}</div>
                  <div className="notif-item-content">
                    <div className="notif-item-title">{n.title}</div>
                    <div className="notif-item-desc">{n.desc}</div>
                    <div className="notif-item-time">{n.time}</div>
                  </div>
                </div>
              ))}
              {unread > 0 && (
                <button
                  className="msg-action-btn"
                  style={{ margin: "8px auto", display: "block" }}
                  onClick={markAllRead}
                  type="button"
                >
                  全部已读
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function addNotification(title: string, desc: string) {
  const notifs: NotifItem[] = loadNotifs();
  notifs.unshift({
    id: crypto.randomUUID(),
    title,
    desc,
    time: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
    read: false,
  });
  localStorage.setItem(NOTIFS_KEY, JSON.stringify(notifs.slice(0, 100)));
}

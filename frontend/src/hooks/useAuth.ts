import { useCallback } from "react";
import { apiGet, apiPost, clearAccessToken, getAccessToken, setAccessToken } from "../api/client";
import { useAppContext } from "../context/AppContext";
import type {
  BaseAgentProfile,
  ConversationSession,
  LoginResponse,
  Recommendation,
  StudentProfile,
  UserDTO,
} from "../types/baseline";

export function useAuth() {
  const { state, dispatch } = useAppContext();

  const loadUserBundle = useCallback(async () => {
    const me = await apiGet<UserDTO>("/auth/me");
    dispatch({ type: "SET_USER", payload: me });

    // Each call is isolated — a 404 on profile won't break conversations
    let nextProfile: StudentProfile | null = null;
    try { nextProfile = await apiGet<StudentProfile>(`/profiles/me`); } catch { /* new user, no profile yet */ }
    if (nextProfile) dispatch({ type: "SET_PROFILE", payload: nextProfile });

    let nextBaseAgents: BaseAgentProfile[] = [];
    try { nextBaseAgents = await apiGet<BaseAgentProfile[]>(`/agents/base-agents`); } catch { /* ignore */ }
    dispatch({ type: "SET_AGENTS", payload: nextBaseAgents });

    let nextConversations: { conversations: ConversationSession[] } = { conversations: [] };
    try { nextConversations = await apiGet<{ conversations: ConversationSession[] }>(`/conversations/users/me/list`); } catch { /* ignore */ }
    dispatch({ type: "SET_CONVERSATIONS", payload: nextConversations.conversations ?? [] });

    let nextRecommendations: Recommendation[] = [];
    try { nextRecommendations = await apiGet<Recommendation[]>(`/recommendations/`); } catch { /* ignore */ }
    dispatch({ type: "SET_RECOMMENDATIONS", payload: nextRecommendations });

    dispatch({ type: "SET_SELECTED_AGENT", payload: nextBaseAgents[0]?.agent_id ?? null });
    dispatch({ type: "SET_SELECTED_CONVERSATION", payload: nextConversations.conversations[0]?.conversation_id ?? null });
    dispatch({ type: "SET_NOTICE", payload: "学习画像、历史会话和智能体已加载。" });
  }, [dispatch]);

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await apiPost<LoginResponse>("/auth/login", { username, password });
      setAccessToken(response.access_token);
      dispatch({ type: "SET_USER", payload: response.user });
      await loadUserBundle();
    },
    [dispatch, loadUserBundle]
  );

  const register = useCallback(
    async (payload: {
      username: string;
      password: string;
      real_name?: string;
      major?: string;
      grade?: string;
      school?: string;
    }) => {
      const response = await apiPost<LoginResponse>("/auth/register", payload);
      setAccessToken(response.access_token);
      dispatch({ type: "SET_USER", payload: response.user });
      await loadUserBundle();
    },
    [dispatch, loadUserBundle]
  );

  const logout = useCallback(() => {
    clearAccessToken();
    dispatch({ type: "LOGOUT" });
  }, [dispatch]);

  const initAuth = useCallback(async () => {
    if (!getAccessToken()) return false;
    try {
      await loadUserBundle();
      return true;
    } catch {
      return false;
    }
  }, [loadUserBundle]);

  return { user: state.user, login, register, logout, loadUserBundle, initAuth };
}

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
    let me: UserDTO;
    try {
      me = await apiGet<UserDTO>("/auth/me");
    } catch (err) {
      dispatch({ type: "SET_NOTICE", payload: "加载用户信息失败，请重新登录。" });
      throw err;
    }
    dispatch({ type: "SET_USER", payload: me });

    // Fire all remaining requests in parallel — each is isolated
    const [nextProfile, nextBaseAgents, nextConversations, nextRecommendations] = await Promise.all([
      apiGet<StudentProfile>(`/profiles/me`).catch(() => null),
      apiGet<BaseAgentProfile[]>(`/agents/base-agents`).catch(() => []),
      apiGet<{ conversations: ConversationSession[] }>(`/conversations/users/me/list`).catch(() => ({ conversations: [] })),
      apiGet<Recommendation[]>(`/recommendations/`).catch(() => []),
    ]);

    if (nextProfile) {
      dispatch({ type: "SET_PROFILE", payload: nextProfile });
    }
    dispatch({ type: "MARK_PROFILE_LOADED" });
    dispatch({ type: "SET_AGENTS", payload: nextBaseAgents });
    dispatch({ type: "SET_CONVERSATIONS", payload: nextConversations.conversations ?? [] });
    dispatch({ type: "SET_RECOMMENDATIONS", payload: nextRecommendations });

    dispatch({ type: "SET_SELECTED_AGENT", payload: nextBaseAgents[0]?.agent_id ?? null });
    dispatch({ type: "SET_SELECTED_CONVERSATION", payload: nextConversations.conversations[0]?.conversation_id ?? null });
    dispatch({ type: "SET_NOTICE", payload: "学习画像、历史会话和智能体已加载。" });
  }, [dispatch]);

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await apiPost<LoginResponse>("/auth/login", { username, password });
      setAccessToken(response.access_token);
      // loadUserBundle dispatches SET_USER from /auth/me — no need to dispatch here
      await loadUserBundle();
    },
    [loadUserBundle]
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
      // loadUserBundle dispatches SET_USER from /auth/me — no need to dispatch here
      await loadUserBundle();
    },
    [loadUserBundle]
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

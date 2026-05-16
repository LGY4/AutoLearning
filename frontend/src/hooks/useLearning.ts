import { useCallback, useRef } from "react";
import { apiGet, apiPost } from "../api/client";
import { useAppContext, EMPTY_PROFILE, EMPTY_PATH } from "../context/AppContext";
import type { ConversationSession } from "../context/AppContext";
import type { LearningResource, StudentProfile } from "../types/baseline";

export function useLearning() {
  const { dispatch } = useAppContext();
  const loadSeqRef = useRef(0);

  const loadConversation = useCallback(
    async (conversationId: string) => {
      const seq = ++loadSeqRef.current;

      dispatch({ type: "SET_PROFILE", payload: EMPTY_PROFILE });
      dispatch({ type: "SET_PATH", payload: EMPTY_PATH });
      dispatch({ type: "SET_RESOURCES", payload: [] });

      const session = await apiGet<ConversationSession>(`/conversations/${conversationId}`);
      if (loadSeqRef.current !== seq) return;

      dispatch({ type: "SET_SELECTED_CONVERSATION", payload: session.conversation_id });
      dispatch({ type: "SET_ACTIVE_MESSAGES", payload: session.messages ?? [] });

      if (session.profile_id) {
        try {
          const profile = await apiGet<StudentProfile>(`/profiles/profile/${session.profile_id}`);
          if (loadSeqRef.current !== seq) return;
          dispatch({ type: "SET_PROFILE", payload: profile });
        } catch {
          // profile not found
        }
      }

      const resourceIds: string[] = [];
      for (const msg of session.messages) {
        if (msg.role === "assistant" && msg.metadata?.resource_ids) {
          const ids = msg.metadata.resource_ids;
          if (Array.isArray(ids)) resourceIds.push(...ids.map(String));
        }
      }
      if (resourceIds.length > 0) {
        try {
          const resources = await apiPost<LearningResource[]>("/resources/batch", { resource_ids: resourceIds });
          if (loadSeqRef.current !== seq) return;
          dispatch({ type: "SET_RESOURCES", payload: resources });
        } catch {
          // keep empty
        }
      }
    },
    [dispatch]
  );

  return { loadConversation };
}

import { useCallback } from "react";
import { apiPost } from "../api/client";
import { useAppContext } from "../context/AppContext";

export function useRecordLearning() {
  const { state } = useAppContext();

  return useCallback(
    async (payload: {
      knowledge_point: string;
      resource_type: string;
      score: number;
      duration_seconds?: number;
      wrong_points?: string[];
      feedback?: string;
    }) => {
      if (!state.user) return;
      try {
        await apiPost("/learning-records", {
          user_id: state.user.id,
          knowledge_point: payload.knowledge_point,
          resource_type: payload.resource_type,
          score: payload.score,
          duration_seconds: payload.duration_seconds ?? 0,
          wrong_points: payload.wrong_points ?? [],
          feedback: payload.feedback,
        });
      } catch {
        // fire-and-forget
      }
    },
    [state.user]
  );
}

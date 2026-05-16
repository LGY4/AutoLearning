import { useCallback, useRef, useState } from "react";
import { apiGet } from "../api/client";

export interface TaskStatus {
  celery_task_id?: string;
  task_id?: string;
  status: "pending" | "running" | "done" | "failed" | string;
  progress?: Array<Record<string, unknown>>;
  result: Record<string, unknown> | null;
  error?: string | null;
  message?: string;
}

interface UseTaskPollingOptions {
  intervalMs?: number;
  maxAttempts?: number;
  onDone?: (result: Record<string, unknown>) => void;
  onError?: (error: string) => void;
}

export function useTaskPolling(options: UseTaskPollingOptions = {}) {
  const { intervalMs = 2000, maxAttempts = 150, onDone, onError } = options;
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setPolling(false);
  }, []);

  const startPolling = useCallback((taskId: string) => {
    stopPolling();
    setPolling(true);
    attemptsRef.current = 0;

    const poll = async () => {
      attemptsRef.current += 1;
      try {
        const status = await apiGet<TaskStatus>(`/resources/tasks/${taskId}`);
        setTaskStatus(status);

        if (status.status === "done") {
          stopPolling();
          onDone?.(status.result ?? {});
          return;
        }
        if (status.status === "failed") {
          stopPolling();
          const errMsg = status.error ?? (status.result as Record<string, unknown>)?.message as string ?? status.message ?? "任务失败";
          onError?.(errMsg);
          return;
        }
        if (attemptsRef.current >= maxAttempts) {
          stopPolling();
          onError?.("任务超时");
          return;
        }
      } catch (e) {
        if (attemptsRef.current >= maxAttempts) {
          stopPolling();
          onError?.(e instanceof Error ? e.message : "轮询失败");
        }
      }
    };

    poll();
    timerRef.current = setInterval(poll, intervalMs);
  }, [intervalMs, maxAttempts, onDone, onError, stopPolling]);

  return { taskStatus, polling, startPolling, stopPolling };
}

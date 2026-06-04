import { useCallback, useEffect, useRef, useState } from "react";
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
  endpoint?: string;  // e.g. "/video/status", "/system/media/status"
  onDone?: (result: Record<string, unknown>) => void;
  onError?: (error: string) => void;
}

export function useTaskPolling(options: UseTaskPollingOptions = {}) {
  const { intervalMs = 2000, maxAttempts = 150, endpoint = "/resources/tasks" } = options;
  const onDoneRef = useRef(options.onDone);
  const onErrorRef = useRef(options.onError);
  onDoneRef.current = options.onDone;
  onErrorRef.current = options.onError;

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
        const status = await apiGet<TaskStatus>(`${endpoint}/${taskId}`);
        setTaskStatus(status);

        if (status.status === "done") {
          stopPolling();
          onDoneRef.current?.(status.result ?? {});
          return;
        }
        if (status.status === "failed") {
          stopPolling();
          const errMsg = status.error ?? (status.result as Record<string, unknown>)?.message as string ?? status.message ?? "任务失败";
          onErrorRef.current?.(errMsg);
          return;
        }
        if (attemptsRef.current >= maxAttempts) {
          stopPolling();
          onErrorRef.current?.("任务超时");
          return;
        }
      } catch (e) {
        if (attemptsRef.current >= maxAttempts) {
          stopPolling();
          onErrorRef.current?.(e instanceof Error ? e.message : "轮询失败");
        }
      }
    };

    poll();
    timerRef.current = setInterval(poll, intervalMs);
  }, [intervalMs, maxAttempts, stopPolling]);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  return { taskStatus, polling, startPolling, stopPolling };
}

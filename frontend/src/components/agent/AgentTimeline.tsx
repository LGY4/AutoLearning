import { CheckCircle2, Clock, Loader2, XCircle, GitBranch } from "lucide-react";
import { Progress } from "antd";
import type { AgentEvent, AgentTask } from "../../types/baseline";

interface Props {
  tasks: AgentTask[];
  events?: AgentEvent[];
}

const STATUS_ICONS: Record<string, typeof CheckCircle2> = {
  pending: Clock,
  running: Loader2,
  success: CheckCircle2,
  completed: CheckCircle2,
  failed: XCircle,
  retrying: Loader2,
  cancelled: XCircle,
  timeout: Clock,
};

export function AgentTimeline({ tasks, events = [] }: Props) {
  return (
    <section className="panel">
      <div className="panel-title">
        <GitBranch size={20} />
        <h2>Agent 协作过程</h2>
      </div>
      <div className="agent-list">
        {tasks.map((task, index) => {
          const event = events.find((item) => item.task_id === task.task_id);
          const StatusIcon = STATUS_ICONS[task.status] ?? CheckCircle2;
          const isRunning = task.status === "running" || task.status === "retrying";
          return (
            <div className="agent-step" key={task.task_id}>
              <div className="step-index">{index + 1}</div>
              <div>
                <strong>{task.agent_name}</strong>
                <span>
                  {event?.action ?? task.task_type} · {task.progress}% · {task.duration_ms ?? event?.duration_ms ?? 0}ms
                </span>
                <Progress percent={event?.progress ?? task.progress} size="small" showInfo={false} />
                {task.error_message && <span className="agent-error">{task.error_message}</span>}
              </div>
              <StatusIcon size={18} className={isRunning ? "agent-status-spinning" : ""} />
            </div>
          );
        })}
      </div>
    </section>
  );
}

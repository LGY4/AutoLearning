import { useMemo } from "react";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { TraceEntry } from "../chat/ChatMessage";

interface PipelineStep {
  node: string;
  label: string;
  icon: string;
}

const PIPELINE_STEPS: PipelineStep[] = [
  { node: "profile_agent", label: "画像", icon: "👤" },
  { node: "path_agent", label: "路径", icon: "🗺️" },
  { node: "gen_document", label: "文档", icon: "📄" },
  { node: "gen_mindmap", label: "导图", icon: "🧠" },
  { node: "gen_quiz", label: "测验", icon: "📝" },
  { node: "gen_code_case", label: "代码", icon: "💻" },
  { node: "gen_video", label: "视频", icon: "🎬" },
  { node: "gen_animation", label: "动画", icon: "🎞️" },
  { node: "gen_reading", label: "阅读", icon: "📖" },
  { node: "quality_agent", label: "质量", icon: "✅" },
  { node: "recommendation_agent", label: "推荐", icon: "💡" },
];

interface Props {
  trace: TraceEntry[];
  streaming: boolean;
  currentAgent?: string;
}

function getStepStatus(node: string, trace: TraceEntry[], currentAgent: string): "done" | "running" | "failed" | "pending" {
  const entries = trace.filter((e) => e.node === node);
  if (entries.length === 0) {
    if (currentAgent.includes(node) || currentAgent.includes(PIPELINE_STEPS.find((s) => s.node === node)?.label ?? "")) return "running";
    return "pending";
  }
  const latest = entries[entries.length - 1];
  if (latest.status === "done" || latest.status === "success") return "done";
  if (latest.status === "failed" || latest.status === "error") return "failed";
  return "running";
}

function getDuration(node: string, trace: TraceEntry[]): number {
  const entries = trace.filter((e) => e.node === node && e.duration_ms > 0);
  return entries.length > 0 ? entries[entries.length - 1].duration_ms : 0;
}

export function PipelineBar({ trace, streaming, currentAgent = "" }: Props) {
  const activeSteps = useMemo(() => {
    const activeNodes = new Set(trace.map((e) => e.node));
    return PIPELINE_STEPS.filter((s) => activeNodes.has(s.node) || (streaming && s.node === "profile_agent"));
  }, [trace, streaming]);

  if (activeSteps.length === 0) return null;

  const doneCount = activeSteps.filter((s) => getStepStatus(s.node, trace, currentAgent) === "done").length;
  const progressPct = Math.round((doneCount / activeSteps.length) * 100);
  const isComplete = doneCount === activeSteps.length;

  const runningStep = activeSteps.find((s) => getStepStatus(s.node, trace, currentAgent) === "running");

  return (
    <div className={`pipeline-bar ${isComplete ? "complete" : ""}`}>
      <div className="pipeline-steps">
        {activeSteps.map((step, i) => {
          const status = getStepStatus(step.node, trace, currentAgent);
          const duration = getDuration(step.node, trace);
          return (
            <div key={step.node} className="pipeline-step-group">
              {i > 0 && <div className={`pipeline-connector ${status === "done" || status === "running" ? "active" : ""}`} />}
              <div className={`pipeline-step ${status}`}>
                <div className="pipeline-step-icon">
                  {status === "done" ? <CheckCircle2 size={16} /> :
                   status === "running" ? <Loader2 size={16} className="pipeline-spin" /> :
                   status === "failed" ? <XCircle size={16} /> :
                   <Circle size={16} />}
                </div>
                <span className="pipeline-step-label">{step.label}</span>
                {duration > 0 && <span className="pipeline-step-time">{duration >= 1000 ? `${(duration / 1000).toFixed(1)}s` : `${duration}ms`}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="pipeline-progress-track">
        <div className="pipeline-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>
      <div className="pipeline-status-text">
        {isComplete ? (
          <span className="pipeline-done">全部完成</span>
        ) : runningStep ? (
          <span>{runningStep.icon} {runningStep.label} 生成中...</span>
        ) : (
          <span>准备中...</span>
        )}
        <span className="pipeline-pct">{progressPct}%</span>
      </div>
    </div>
  );
}

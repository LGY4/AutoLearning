import type { TraceEntry } from "../chat/ChatMessage";

interface Props {
  trace: TraceEntry[];
}

function StatusIcon({ status }: { status: string }) {
  if (status === "running") {
    return <span className="agent-trace-icon spinning">&#8987;</span>;
  }
  if (status === "done") {
    return <span className="agent-trace-icon done">&#10003;</span>;
  }
  if (status === "failed") {
    return <span className="agent-trace-icon failed">&#10007;</span>;
  }
  return null;
}

function isGenNode(node: string) {
  return node.startsWith("gen_");
}

function TraceEntryView({ entry }: { entry: TraceEntry }) {
  return (
    <div className={`agent-trace-entry ${entry.status}`}>
      <StatusIcon status={entry.status} />
      <span className="agent-trace-hint">{entry.hint}</span>
      {entry.status !== "running" && entry.duration_ms > 0 && (
        <span className="agent-trace-duration">{entry.duration_ms}ms</span>
      )}
    </div>
  );
}

export function AgentTrace({ trace }: Props) {
  // Group consecutive gen_* nodes into a parallel block
  const rows: React.ReactNode[] = [];
  let i = 0;
  while (i < trace.length) {
    if (isGenNode(trace[i].node)) {
      const group: TraceEntry[] = [];
      while (i < trace.length && isGenNode(trace[i].node)) {
        group.push(trace[i]);
        i++;
      }
      rows.push(
        <div className="agent-trace-parallel" key={`par-${i}`}>
          <div className="agent-trace-parallel-label">并行生成</div>
          <div className="agent-trace-parallel-items">
            {group.map((entry, j) => (
              <TraceEntryView key={j} entry={entry} />
            ))}
          </div>
        </div>
      );
    } else {
      rows.push(<TraceEntryView key={i} entry={trace[i]} />);
      i++;
    }
  }

  return <div className="agent-trace">{rows}</div>;
}

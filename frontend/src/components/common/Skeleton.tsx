interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}

export function Skeleton({ width = "100%", height = 16, borderRadius = 4, style }: SkeletonProps) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius,
        background: "var(--bg-card-hover)",
        animation: "skeleton-pulse 1.5s ease-in-out infinite",
        ...style,
      }}
    />
  );
}

export function ChatSkeleton() {
  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <Skeleton width={32} height={32} borderRadius="50%" />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
          <Skeleton width="60%" height={14} />
          <Skeleton width="90%" height={14} />
          <Skeleton width="40%" height={14} />
        </div>
      </div>
    </div>
  );
}

export function ResourceSkeleton() {
  return (
    <div style={{ padding: 12, border: "1px solid var(--border-primary)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 8 }}>
      <Skeleton width="70%" height={16} />
      <Skeleton width="100%" height={12} />
      <Skeleton width="80%" height={12} />
      <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
        <Skeleton width={60} height={24} borderRadius={12} />
        <Skeleton width={80} height={24} borderRadius={12} />
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{ padding: 12, border: "1px solid var(--border-primary)", borderRadius: 8 }}>
            <Skeleton width="50%" height={12} />
            <Skeleton width="80%" height={24} style={{ marginTop: 8 }} />
          </div>
        ))}
      </div>
      <Skeleton width="100%" height={200} borderRadius={8} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} width="100%" height={40} borderRadius={8} />
        ))}
      </div>
    </div>
  );
}

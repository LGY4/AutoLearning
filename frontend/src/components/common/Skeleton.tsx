export function Skeleton({ width, height, count = 1 }: { width?: string; height?: string; count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="skeleton"
          style={{
            width: width || "100%",
            height: height || "16px",
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
    </>
  );
}

export function PageSkeleton({ lines = 6 }: { lines?: number }) {
  return (
    <div className="page-container" style={{ display: "flex", flexDirection: "column", gap: 16, padding: 24 }}>
      <Skeleton width="40%" height="28px" />
      <Skeleton height="80px" />
      <Skeleton height="60px" count={lines - 1} />
    </div>
  );
}

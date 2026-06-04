export const DIM_KEYS = ["mastery", "application", "memory", "understanding"] as const;

export const DIM_LABELS: Record<string, string> = {
  mastery: "掌握",
  application: "应用",
  memory: "记忆",
  understanding: "理解",
};

export function dimToValue(dim: string): number {
  if (dim === "high") return 1.0;
  if (dim === "mid") return 0.6;
  return 0.3;
}

interface Props {
  dimensions: Record<string, number>;
  size?: number;
}

export function RadarChart({ dimensions, size = 160 }: Props) {
  const cx = size / 2, cy = size / 2, r = size / 2 - 20;
  const angles = [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2];
  const labels = ["掌握", "应用", "记忆", "理解"];
  const values = DIM_KEYS.map((k) => dimensions[k] ?? 0.33);

  const points = values.map((v, i) => {
    const angle = angles[i] - Math.PI / 2;
    const px = cx + r * v * Math.cos(angle);
    const py = cy + r * v * Math.sin(angle);
    return `${px},${py}`;
  });

  const gridLevels = [0.33, 0.67, 1.0];

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ margin: "8px auto", display: "block" }}>
      {gridLevels.map((level) => (
        <polygon
          key={level}
          points={angles.map((a) => {
            const angle = a - Math.PI / 2;
            return `${cx + r * level * Math.cos(angle)},${cy + r * level * Math.sin(angle)}`;
          }).join(" ")}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="1"
        />
      ))}
      {angles.map((a, i) => {
        const angle = a - Math.PI / 2;
        const lx = cx + r * Math.cos(angle);
        const ly = cy + r * Math.sin(angle);
        return <line key={i} x1={cx} y1={cy} x2={lx} y2={ly} stroke="rgba(255,255,255,0.15)" strokeWidth="1" />;
      })}
      <polygon
        points={points.join(" ")}
        fill="rgba(96,165,250,0.25)"
        stroke="#60a5fa"
        strokeWidth="2"
      />
      {points.map((p, i) => {
        const [px, py] = p.split(",").map(Number);
        return <circle key={i} cx={px} cy={py} r="3" fill="#60a5fa" />;
      })}
      {angles.map((a, i) => {
        const angle = a - Math.PI / 2;
        const lx = cx + (r + 16) * Math.cos(angle);
        const ly = cy + (r + 16) * Math.sin(angle);
        return (
          <text
            key={i}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="central"
            fill="rgba(255,255,255,0.7)"
            fontSize="11"
          >
            {labels[i]}
          </text>
        );
      })}
    </svg>
  );
}

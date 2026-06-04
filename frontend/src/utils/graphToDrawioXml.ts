/**
 * Graph data → draw.io XML conversion for the learning map.
 * Pure utility — no React dependencies.
 */

interface GraphNode {
  id: string;
  name: string;
  depends_on?: string[];
  next_nodes?: string[];
  path_status?: { node_id: string; order: number; status: string; estimated_minutes: number } | null;
}

interface GraphEdge {
  from: string;
  to: string;
}

// ── Status color config ──────────────────────────────────────────────

export const STATUS_COLORS: Record<string, { fill: string; stroke: string; fontColor: string }> = {
  locked:    { fill: "#374151", stroke: "#6b7280", fontColor: "#9ca3af" },
  available: { fill: "#1e3a5f", stroke: "#3b82f6", fontColor: "#bfdbfe" },
  learning:  { fill: "#451a03", stroke: "#f59e0b", fontColor: "#fde68a" },
  completed: { fill: "#052e16", stroke: "#22c55e", fontColor: "#86efac" },
  skipped:   { fill: "#1f2937", stroke: "#9ca3af", fontColor: "#d1d5db" },
};

// ── Layout constants ─────────────────────────────────────────────────

const NODE_W = 160;
const NODE_H = 60;
const NODE_PAD = 30;
const LEVEL_PAD = 60;
const CANVAS_PAD = 40;

// ── Helpers ──────────────────────────────────────────────────────────

function escapeXml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

// ── Topological sort → levels ────────────────────────────────────────

export function computeLevels(nodes: GraphNode[], edges: GraphEdge[]): GraphNode[][] {
  if (nodes.length === 0) return [];

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const inDegree = new Map<string, number>();
  nodes.forEach((n) => inDegree.set(n.id, 0));
  edges.forEach((e) => inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1));

  const levels: GraphNode[][] = [];
  const assigned = new Set<string>();
  let current = nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0);

  while (current.length > 0) {
    levels.push(current);
    current.forEach((n) => assigned.add(n.id));
    const next: GraphNode[] = [];
    current.forEach((n) => {
      (n.next_nodes ?? []).forEach((nid) => {
        if (!assigned.has(nid)) {
          const node = nodeMap.get(nid);
          if (node && !next.includes(node)) next.push(node);
        }
      });
    });
    current = next;
  }

  const orphan = nodes.filter((n) => !assigned.has(n.id));
  if (orphan.length > 0) levels.push(orphan);

  return levels;
}

// ── Generate draw.io XML ─────────────────────────────────────────────

export function generateLearningMapXml(
  levels: GraphNode[][],
  edges: GraphEdge[],
  getNodeStatus: (node: GraphNode) => string,
): string {
  if (levels.length === 0) return "";

  // Compute canvas width from widest level
  const maxPerLevel = Math.max(...levels.map((l) => l.length));
  const canvasWidth = Math.max(maxPerLevel * (NODE_W + NODE_PAD) - NODE_PAD + CANVAS_PAD * 2, 400);

  const cells: string[] = [];
  let idCounter = 2;

  // Map node data ID → mxCell ID for edge references
  const nodeIdToCellId = new Map<string, number>();

  levels.forEach((level, li) => {
    const levelWidth = level.length * (NODE_W + NODE_PAD) - NODE_PAD;
    const x0 = CANVAS_PAD + (canvasWidth - levelWidth) / 2;
    const y = CANVAS_PAD + li * (NODE_H + LEVEL_PAD);

    level.forEach((node, ni) => {
      const x = x0 + ni * (NODE_W + NODE_PAD);
      const status = getNodeStatus(node);
      const colors = STATUS_COLORS[status] ?? STATUS_COLORS.locked;
      const id = idCounter++;

      const style = [
        "rounded=1",
        "whiteSpace=wrap",
        "html=1",
        `fillColor=${colors.fill}`,
        `strokeColor=${colors.stroke}`,
        `fontColor=${colors.fontColor}`,
        "fontFamily=Microsoft YaHei",
        "fontSize=13",
        "fontStyle=1",
        "verticalAlign=middle",
        "align=center",
        "spacingTop=8",
      ].join(";");

      cells.push(
        `<mxCell id="${id}" value="${escapeXml(node.name)}" style="${style};" vertex="1" parent="1" link="node:${node.id}">` +
          `<mxGeometry x="${x}" y="${y}" width="${NODE_W}" height="${NODE_H}" as="geometry"/>` +
        `</mxCell>`
      );

      nodeIdToCellId.set(node.id, id);
    });
  });

  // Generate edge cells
  const edgeStyle = "curved=1;endArrow=block;endFill=1;strokeColor=#4b5563;strokeWidth=1.5;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;";

  edges.forEach((e) => {
    const srcId = nodeIdToCellId.get(e.from);
    const tgtId = nodeIdToCellId.get(e.to);
    if (srcId == null || tgtId == null) return;
    const id = idCounter++;
    cells.push(
      `<mxCell id="${id}" style="${edgeStyle}" edge="1" parent="1" source="${srcId}" target="${tgtId}">` +
        `<mxGeometry relative="1" as="geometry"/>` +
      `</mxCell>`
    );
  });

  // Wrap in mxfile structure
  const diagramId = `learning-map-${Date.now()}`;
  return [
    `<mxfile host="app.diagrams.net" type="device">`,
    `<diagram id="${diagramId}" name="Learning Map">`,
    `<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="${canvasWidth}" pageHeight="${CANVAS_PAD * 2 + levels.length * (NODE_H + LEVEL_PAD)}">`,
    `<root>`,
    `<mxCell id="0"/>`,
    `<mxCell id="1" parent="0"/>`,
    ...cells,
    `</root>`,
    `</mxGraphModel>`,
    `</diagram>`,
    `</mxfile>`,
  ].join("\n");
}

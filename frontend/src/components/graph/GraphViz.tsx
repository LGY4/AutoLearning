import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

interface GraphNode {
  id: string;
  name: string;
  level: number;
  depends_on: string[];
  description: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  className?: string;
}

const LEVEL_COLORS: Record<number, string> = {
  0: "#6366f1",
  1: "#8b5cf6",
  2: "#a78bfa",
  3: "#c4b5fd",
  4: "#ddd6fe",
};

export function GraphViz({ nodes, edges, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const elements: cytoscape.ElementDefinition[] = [];

    for (const n of nodes) {
      elements.push({
        data: {
          id: n.id,
          label: n.name,
          level: n.level,
        },
      });
    }

    for (const e of edges) {
      elements.push({
        data: {
          source: e.source,
          target: e.target,
          edgeType: e.type,
        },
      });
    }

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": (ele: cytoscape.NodeSingular) =>
              LEVEL_COLORS[ele.data("level") as number] || "#6366f1",
            color: "#e2e8f0",
            "font-size": "11px",
            "text-valign": "bottom",
            "text-margin-y": 6,
            "text-wrap": "wrap",
            "text-max-width": "80px",
            width: 28,
            height: 28,
            "border-width": 2,
            "border-color": "rgba(255,255,255,0.15)",
          } as cytoscape.Css.Node,
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "rgba(255, 255, 255, 0.2)",
            "target-arrow-color": "rgba(255, 255, 255, 0.2)",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          } as cytoscape.Css.Edge,
        },
        {
          selector: 'edge[edgeType="prerequisite"]',
          style: {
            "line-color": "rgba(99, 102, 241, 0.4)",
            "target-arrow-color": "rgba(99, 102, 241, 0.4)",
            "line-style": "solid",
          } as cytoscape.Css.Edge,
        },
      ],
      layout: {
        name: "breadthfirst",
        directed: true,
        padding: 30,
        spacingFactor: 1.2,
        animate: true,
        animationDuration: 400,
      } as cytoscape.LayoutOptions,
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, [nodes, edges]);

  if (nodes.length === 0) {
    return <div className={className} style={{ color: "rgba(255,255,255,0.3)", textAlign: "center", padding: 40 }}>无节点数据</div>;
  }

  return (
    <div className={className}>
      <div ref={containerRef} className="cytoscape-container" />
      <div className="graph-viz-legend">
        {Object.entries(LEVEL_COLORS).map(([level, color]) => (
          <div key={level} className="graph-viz-legend-item">
            <span className="graph-viz-legend-dot" style={{ background: color }} />
            <span>L{level}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

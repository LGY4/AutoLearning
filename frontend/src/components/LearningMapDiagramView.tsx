import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DrawIoEmbed } from "react-drawio";
import type { DrawIoEmbedRef, EventExport } from "react-drawio/dist/types";
import { jsPDF } from "jspdf";
import "svg2pdf.js";
import { generateLearningMapXml } from "../utils/graphToDrawioXml";

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

type ExportFmt = "png" | "svg" | "pdf";

interface Props {
  levels: GraphNode[][];
  edges: GraphEdge[];
  getNodeStatus: (node: GraphNode) => string;
  onSelectNode: (node: GraphNode) => void;
  nodeMap: Map<string, GraphNode>;
}

export function LearningMapDiagramView({ levels, edges, getNodeStatus, onSelectNode, nodeMap }: Props) {
  const drawioRef = useRef<DrawIoEmbedRef | null>(null);
  const [ready, setReady] = useState(false);
  const readyRef = useRef(false);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<ExportFmt>("png");
  const [error, setError] = useState<string | null>(null);
  // Ref to capture format at request time, avoiding stale closure in onExport callback
  const pendingFormatRef = useRef<ExportFmt>("png");

  // Generate XML from graph data
  const xml = useMemo(
    () => generateLearningMapXml(levels, edges, getNodeStatus),
    [levels, edges, getNodeStatus],
  );

  // Timeout if iframe doesn't load
  useEffect(() => {
    if (!xml || readyRef.current) return;
    const timer = setTimeout(() => {
      if (!readyRef.current) setError("图表加载超时，请检查网络连接或刷新重试");
    }, 15_000);
    return () => clearTimeout(timer);
  }, [xml]);

  // Listen for draw.io link click events (node selection)
  useEffect(() => {
    const handler = (evt: MessageEvent) => {
      if (typeof evt.data !== "string") return;
      try {
        const data = JSON.parse(evt.data);
        if (data.event === "link" && typeof data.url === "string") {
          const match = data.url.match(/^node:(.+)$/);
          if (match) {
            const node = nodeMap.get(match[1]);
            if (node) onSelectNode(node);
          }
        }
      } catch { /* not JSON, ignore */ }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [nodeMap, onSelectNode]);

  const handleLoad = useCallback(() => {
    setReady(true);
    readyRef.current = true;
  }, []);

  const handleExport = useCallback(async (data: EventExport) => {
    setExporting(false);
    if (!data.data) return;
    // Use the format captured at request time, not the current state
    const fmt = pendingFormatRef.current;
    const link = document.createElement("a");
    if (fmt === "png") {
      link.href = `data:image/png;base64,${data.data}`;
      link.download = "learning-map.png";
      link.click();
    } else if (fmt === "svg") {
      const blob = new Blob([data.data], { type: "image/svg+xml;charset=utf-8" });
      const blobUrl = URL.createObjectURL(blob);
      link.href = blobUrl;
      link.download = "learning-map.svg";
      link.click();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } else if (fmt === "pdf") {
      try {
        const parser = new DOMParser();
        const svgDoc = parser.parseFromString(data.data, "image/svg+xml");
        const svgEl = svgDoc.documentElement;
        const w = parseFloat(svgEl.getAttribute("width") || "800");
        const h = parseFloat(svgEl.getAttribute("height") || "600");
        const pdf = new jsPDF({ orientation: w > h ? "landscape" : "portrait", unit: "px", format: [w, h] });
        await (pdf as any).svg(svgEl, { x: 0, y: 0, width: w, height: h });
        pdf.save("learning-map.pdf");
      } catch {
        alert("PDF 导出失败，请尝试 PNG 或 SVG");
      }
    }
  }, []);

  const handleExportClick = useCallback(() => {
    if (drawioRef.current) {
      pendingFormatRef.current = exportFormat;
      setExporting(true);
      drawioRef.current.exportDiagram({ format: exportFormat === "pdf" ? "svg" : exportFormat });
    }
  }, [exportFormat]);

  if (error) {
    return <div className="flowchart-container flowchart-error"><span>{error}</span></div>;
  }

  if (!xml) {
    return <div className="flowchart-container flowchart-error"><span>无图表数据</span></div>;
  }

  return (
    <div className="flowchart-container">
      {!ready && <div className="flowchart-loading">学习地图加载中...</div>}
      <div className="flowchart-toolbar">
        <select className="flowchart-format-select" value={exportFormat}
          onChange={(e) => setExportFormat(e.target.value as ExportFmt)} disabled={exporting}>
          <option value="png">PNG</option>
          <option value="svg">SVG</option>
          <option value="pdf">PDF</option>
        </select>
        <button type="button" className="flowchart-export-btn" onClick={handleExportClick}
          disabled={!ready || exporting}>
          {exporting ? "导出中..." : `导出 ${exportFormat.toUpperCase()}`}
        </button>
      </div>
      <div className="flowchart-embed">
        <DrawIoEmbed
          ref={drawioRef}
          xml={xml}
          urlParameters={{
            lightbox: true,
            nav: true,
            noSaveBtn: true,
            noExitBtn: true,
            spin: true,
          }}
          configuration={{
            defaultLibraries: false,
            libraries: false,
            openLink: "none",
          }}
          exportFormat={exportFormat === "pdf" ? "svg" : exportFormat}
          onLoad={handleLoad}
          onExport={handleExport}
        />
      </div>
    </div>
  );
}

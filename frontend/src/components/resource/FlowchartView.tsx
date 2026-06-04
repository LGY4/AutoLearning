import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DrawIoEmbed } from "react-drawio";
import type { DrawIoEmbedRef, EventExport } from "react-drawio/dist/types";
import { wrapWithMxFile, validateAndFixXml } from "../../utils/drawio-xml";
import { jsPDF } from "jspdf";
import "svg2pdf.js";

type ExportFmt = "png" | "svg" | "pdf";

interface Props {
  content: string;
}

export function FlowchartView({ content }: Props) {
  const drawioRef = useRef<DrawIoEmbedRef | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const readyRef = useRef(false);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<ExportFmt>("png");
  const pendingFormatRef = useRef<ExportFmt>("png");

  // Prepare XML: validate, fix, wrap
  const xml = useMemo(() => {
    if (!content) return "";
    // If content already has mxfile, use as-is
    if (content.includes("<mxfile")) return content;
    // If content has mxCell, wrap it
    if (content.includes("<mxCell")) {
      const { valid, fixed } = validateAndFixXml(content);
      const toWrap = valid ? content : (fixed || content);
      return wrapWithMxFile(toWrap);
    }
    // Might be JSON with drawio_xml field
    try {
      const parsed = JSON.parse(content);
      if (parsed.drawio_xml) {
        const { valid, fixed } = validateAndFixXml(parsed.drawio_xml);
        const toWrap = valid ? parsed.drawio_xml : (fixed || parsed.drawio_xml);
        return wrapWithMxFile(toWrap);
      }
    } catch {
      // Not JSON
    }
    return "";
  }, [content]);

  useEffect(() => {
    if (!xml) {
      setError("无有效的图表数据");
    } else {
      setError(null);
    }
  }, [xml]);

  // Timeout if iframe doesn't load within 15 seconds
  useEffect(() => {
    if (!xml || readyRef.current) return;
    const timer = setTimeout(() => {
      if (!readyRef.current) setError("图表加载超时，请检查网络连接或刷新重试");
    }, 15_000);
    return () => clearTimeout(timer);
  }, [xml]);

  const handleLoad = useCallback(() => {
    setReady(true);
    readyRef.current = true;
  }, []);

  const handleExport = useCallback(async (data: EventExport) => {
    setExporting(false);
    if (!data.data) return;
    const fmt = pendingFormatRef.current;
    const link = document.createElement("a");
    if (fmt === "png") {
      link.href = `data:image/png;base64,${data.data}`;
      link.download = "flowchart.png";
      link.click();
    } else if (fmt === "svg") {
      const blob = new Blob([data.data], { type: "image/svg+xml;charset=utf-8" });
      const blobUrl = URL.createObjectURL(blob);
      link.href = blobUrl;
      link.download = "flowchart.svg";
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
        pdf.save("flowchart.pdf");
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
    return (
      <div className="flowchart-container flowchart-error">
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="flowchart-container">
      {!ready && (
        <div className="flowchart-loading">图表加载中...</div>
      )}
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
            ui: "min",
            noSaveBtn: true,
            noExitBtn: true,
            spin: true,
          }}
          configuration={{
            defaultLibraries: false,
            libraries: false,
          }}
          exportFormat={exportFormat === "pdf" ? "svg" : exportFormat}
          onLoad={handleLoad}
          onExport={handleExport}
        />
      </div>
    </div>
  );
}

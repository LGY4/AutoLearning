import { useCallback, useEffect, useRef, useState } from "react";
import { DrawIoEmbed } from "react-drawio";
import type { DrawIoEmbedRef, EventExport } from "react-drawio/dist/types";
import { wrapWithMxFile, validateAndFixXml } from "../../utils/drawio-xml";

interface Props {
  content: string;
}

export function FlowchartView({ content }: Props) {
  const drawioRef = useRef<DrawIoEmbedRef | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Prepare XML: validate, fix, wrap
  const xml = (() => {
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
  })();

  useEffect(() => {
    if (!xml) {
      setError("无有效的图表数据");
    } else {
      setError(null);
    }
  }, [xml]);

  // Timeout if iframe doesn't load within 15 seconds
  useEffect(() => {
    if (!xml || ready) return;
    const timer = setTimeout(() => {
      if (!ready) setError("图表加载超时，请检查网络连接或刷新重试");
    }, 15_000);
    return () => clearTimeout(timer);
  }, [xml, ready]);

  const handleLoad = useCallback(() => {
    setReady(true);
  }, []);

  const handleExport = useCallback((data: EventExport) => {
    setExporting(false);
    if (!data.data) return;
    // Download as PNG
    const link = document.createElement("a");
    link.href = `data:image/png;base64,${data.data}`;
    link.download = "flowchart.png";
    link.click();
  }, []);

  const handleExportClick = useCallback(() => {
    if (drawioRef.current) {
      setExporting(true);
      drawioRef.current.exportDiagram({ format: "png" });
    }
  }, []);

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
        <button
          type="button"
          className="flowchart-export-btn"
          onClick={handleExportClick}
          disabled={!ready || exporting}
        >
          {exporting ? "导出中..." : "导出 PNG"}
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
          exportFormat="png"
          onLoad={handleLoad}
          onExport={handleExport}
        />
      </div>
    </div>
  );
}

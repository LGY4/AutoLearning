import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const inSet = (pkg: string, values: string[]) => values.includes(pkg);

function getNodeModulePackage(id: string): string | undefined {
  const marker = "/node_modules/";
  const markerIndex = id.lastIndexOf(marker);
  if (markerIndex < 0) return undefined;

  let parts = id.slice(markerIndex + marker.length).split("/");
  const nestedIndex = parts.lastIndexOf("node_modules");
  if (nestedIndex >= 0) parts = parts.slice(nestedIndex + 1);
  if (parts[0]?.startsWith("@")) return parts[1] ? `${parts[0]}/${parts[1]}` : undefined;
  return parts[0];
}

function manualVendorChunk(id: string): string | undefined {
  const pkg = getNodeModulePackage(id.replace(/\\/g, "/"));
  if (!pkg) return undefined;

  if (inSet(pkg, ["react", "react-dom", "scheduler"])) return "react";
  if (pkg === "react-router" || pkg === "react-router-dom") return "router";
  if (pkg === "lucide-react") return "icons";
  if (pkg === "@ant-design/icons") return "antd-icons";
  if (pkg === "antd") return "antd-core";
  if (
    pkg.startsWith("@ant-design/") ||
    pkg.startsWith("@rc-component/") ||
    pkg.startsWith("rc-") ||
    inSet(pkg, [
      "async-validator",
      "classnames",
      "copy-to-clipboard",
      "dayjs",
      "rc-util",
      "scroll-into-view-if-needed",
      "throttle-debounce",
    ])
  ) {
    return "antd-runtime";
  }

  if (inSet(pkg, ["react-syntax-highlighter", "refractor", "prismjs", "lowlight"])) {
    return "code-highlight";
  }

  if (pkg === "katex") return "markmap-katex";
  if (pkg === "yaml") return "markmap-yaml";
  if (
    pkg.startsWith("markmap-") ||
    pkg.startsWith("d3-") ||
    inSet(pkg, [
      "@vscode/markdown-it-katex",
      "argparse",
      "d3",
      "delaunator",
      "highlight.js",
      "internmap",
      "linkify-it",
      "markdown-it",
      "markdown-it-ins",
      "markdown-it-mark",
      "markdown-it-sub",
      "markdown-it-sup",
      "mdurl",
      "punycode.js",
      "resize-observer-polyfill",
      "robust-predicates",
      "uc.micro",
    ])
  ) {
    return "markmap";
  }

  if (
    pkg.startsWith("micromark") ||
    pkg.startsWith("mdast-util") ||
    pkg.startsWith("hast-util") ||
    pkg.startsWith("unist-util") ||
    inSet(pkg, [
      "bail",
      "ccount",
      "character-entities",
      "character-entities-html4",
      "character-entities-legacy",
      "character-reference-invalid",
      "comma-separated-tokens",
      "decode-named-character-reference",
      "devlop",
      "escape-string-regexp",
      "estree-util-is-identifier-name",
      "fault",
      "format",
      "hastscript",
      "html-url-attributes",
      "inline-style-parser",
      "is-alphabetical",
      "is-alphanumerical",
      "is-decimal",
      "is-hexadecimal",
      "is-plain-obj",
      "longest-streak",
      "markdown-table",
      "parse-entities",
      "property-information",
      "react-is",
      "react-markdown",
      "rehype-sanitize",
      "remark-gfm",
      "remark-parse",
      "remark-rehype",
      "space-separated-tokens",
      "style-to-js",
      "style-to-object",
      "trim-lines",
      "trough",
      "unified",
      "vfile",
      "vfile-message",
      "zwitch",
    ])
  ) {
    return "markdown";
  }

  if (pkg === "cytoscape" || pkg === "react-drawio") return "diagram";
  if (pkg === "jspdf") return "export-jspdf";
  if (pkg === "html2canvas") return "export-html2canvas";
  if (inSet(pkg, ["jszip", "pako", "lie", "readable-stream", "setimmediate"])) return "export-zip";
  if (inSet(pkg, ["svg2pdf.js", "cssesc", "font-family-papandreou", "specificity", "svgpath"])) return "export-svg";
  if (
    inSet(pkg, [
      "@babel/runtime",
      "@xmldom/xmldom",
      "base-64",
      "canvg",
      "core-js",
      "css-line-break",
      "dompurify",
      "fast-png",
      "fflate",
      "iobuffer",
      "raf",
      "regenerator-runtime",
      "rgbcolor",
      "stackblur-canvas",
      "svg-pathdata",
      "text-segmentation",
    ])
  ) {
    return "export-runtime";
  }

  if (pkg === "react-virtuoso") return "virtual-list";
  return "vendor";
}

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: manualVendorChunk,
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": apiProxyTarget,
      "/static": apiProxyTarget,
    },
  },
});

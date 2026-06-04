import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, "/");
          if (!normalizedId.includes("/node_modules/")) {
            return undefined;
          }
          if (
            normalizedId.includes("/react/") ||
            normalizedId.includes("/react-dom/") ||
            normalizedId.includes("/scheduler/")
          ) {
            return "react";
          }
          if (normalizedId.includes("/lucide-react/")) {
            return "icons";
          }
          if (normalizedId.includes("/@ant-design/icons/")) {
            return "antd-icons";
          }
          if (normalizedId.includes("/antd/")) {
            return "antd-core";
          }
          if (
            normalizedId.includes("/@ant-design/") ||
            normalizedId.includes("/rc-") ||
            normalizedId.includes("/@rc-component/")
          ) {
            return "antd-runtime";
          }
          return "vendor";
        }
      }
    }
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": apiProxyTarget,
      "/static": apiProxyTarget
    }
  }
});

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Docker: backend runs at container "backend:8000"
// Local dev: backend runs at "localhost:8000"
export default defineConfig(({ mode }) => {
  // Load .env from project root (one level above frontend/) — same file backend reads.
  // Empty prefix so non-VITE_ vars like DASHBOARD_PORT are exposed.
  const rootEnv = loadEnv(mode, path.resolve(__dirname, ".."), "");
  const backendUrl = rootEnv.VITE_BACKEND_URL || process.env.VITE_BACKEND_URL || "http://localhost:8000";
  const dashboardPort = parseInt(rootEnv.DASHBOARD_PORT || process.env.DASHBOARD_PORT || "3000", 10);

  return {
    plugins: [react()],
    define: {
      __BACKEND_URL__: JSON.stringify(backendUrl),
    },
    server: {
      port: dashboardPort,
      host: "0.0.0.0",
      proxy: {
        "/api": backendUrl,
        "/ws": { target: backendUrl, ws: true },
        "/static": backendUrl,
        "/health": backendUrl,
      },
    },
  };
});

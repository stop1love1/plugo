import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Docker: backend runs at container "backend:8000"
// Local dev: backend runs at "localhost:8000"
const backendUrl = process.env.VITE_BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  define: {
    __BACKEND_URL__: JSON.stringify(backendUrl),
  },
  server: {
    port: 3000,
    host: "0.0.0.0",
    proxy: {
      "/api": backendUrl,
      "/ws": { target: backendUrl, ws: true },
      "/static": backendUrl,
      "/demo": backendUrl,
      "/health": backendUrl,
    },
  },
});

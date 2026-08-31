import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// Dev server proxies the API so the browser sees one origin — no CORS, and the
// admin session cookie is first-party. In production the frontend is served from
// the same origin as the gateway (or behind a reverse proxy).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1, not "localhost" — on Windows the latter can resolve to ::1
      // first and stall if the gateway only bound the IPv4 stack.
      "/v1": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});

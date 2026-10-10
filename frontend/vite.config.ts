import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The browser never talks to the API host directly: /api is proxied to the FastAPI server,
// so no backend URL or secret is embedded in the bundle.
const apiTarget = process.env.GITPULSE_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false, ws: false },
    },
  },
  preview: { host: "0.0.0.0", port: 4173, proxy: { "/api": { target: apiTarget } } },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});

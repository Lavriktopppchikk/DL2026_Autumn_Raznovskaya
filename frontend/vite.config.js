import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Все запросы /api проксируются на бэкенд (FastAPI, порт 8000) — CORS не нужен
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});

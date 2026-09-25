import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In dev, /api is proxied to FastAPI so the browser never talks to Tavily or holds any key.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_BACKEND_URL || "http://localhost:8000", changeOrigin: true } },
  },
});

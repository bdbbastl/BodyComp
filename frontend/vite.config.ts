import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api und /media auf das lokale FastAPI-Backend, damit das
// Frontend im Dev-Modus ohne CORS-Handling gegen relative Pfade arbeitet.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000",
    },
  },
});

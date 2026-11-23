import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend at http://localhost:5178; /api is proxied to the FastAPI backend on :8020.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5178,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8020" },
  },
});

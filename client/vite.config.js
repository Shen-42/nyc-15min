import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development, requests to /api go to the FastAPI server on port 8000.
// This avoids CORS setup while both run on your machine.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

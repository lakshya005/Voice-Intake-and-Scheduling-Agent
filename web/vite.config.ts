import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser talks to Vite; Vite forwards /staff to the FastAPI backend, so the session cookie stays same-origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/staff": "http://localhost:8000" } },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite runs the dashboard on http://localhost:5173 during development.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});

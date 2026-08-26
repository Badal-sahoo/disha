import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // "@/shared/api/client" instead of "../../../shared/api/client".
    // Every import in this project uses the alias -- a feature folder that gets
    // moved should not break twenty relative paths.
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: { port: 5173 },
});

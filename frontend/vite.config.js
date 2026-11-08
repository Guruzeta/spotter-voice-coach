import { defineConfig } from "vite";

const backend = "http://127.0.0.1:8000";

export default defineConfig({
  server: {
    port: 5173,
    proxy: { "/api": backend, "/plots": backend, "/reports": backend },
  },
});

import { defineConfig } from "vite";

const backend = "http://127.0.0.1:8100";

export default defineConfig({
  server: {
    port: 5180,
    proxy: { "/api": backend, "/plots": backend },
  },
});

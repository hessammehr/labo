import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Ketcher uses CJS modules (raphael, draft-js, etc.) that need special
  // handling in Vite's Rollup-based build pipeline.
  // See https://github.com/epam/ketcher/issues/5565
  build: {
    commonjsOptions: {
      include: [
        /ketcher-standalone/,
        /ketcher-react/,
        /raphael/,
        /node_modules/,
      ],
      transformMixedEsModules: true,
    },
  },
  optimizeDeps: {
    include: ["ketcher-core", "ketcher-react", "ketcher-standalone"],
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});

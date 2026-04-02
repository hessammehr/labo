import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // ketcher-react depends on CJS modules (raphael, etc.) that need
  // explicit handling in Vite's Rollup-based production build.
  build: {
    commonjsOptions: {
      include: [/ketcher-react/, /raphael/, /node_modules/],
      transformMixedEsModules: true,
    },
  },
  server: {
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // Base path for GitHub Pages deployment
  // Set to repo name (e.g., "/Botamin-BI/") or "/" for root domain
  base: process.env.NODE_ENV === "production" ? "/Botamin-BI/" : "/",
  build: {
    outDir: "dist",
    sourcemap: false,
    // Generate .nojekyll for GitHub Pages (to allow _ prefixed files)
    emptyOutDir: true,
  },
});

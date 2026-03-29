import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [preact()],
  build: {
    outDir: "widget-dist",
    emptyOutDir: true,
    lib: {
      entry: "src/widget/index.ts",
      name: "PlugoWidget",
      formats: ["iife"],
      fileName: () => "widget.js",
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
    minify: "terser",
    cssCodeSplit: false,
  },
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
});

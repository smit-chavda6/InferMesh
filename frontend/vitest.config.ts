import { defineConfig } from "vitest/config";
import { fileURLToPath, URL } from "node:url";

// Standalone Vitest config. It deliberately does NOT pull in the Vite plugins
// (@vitejs/plugin-react / tailwind) — Vitest transforms JSX with esbuild, which
// is all the tests need, and importing the plugins here trips the Vite 8
// (rolldown) vs. Vitest-bundled-Vite type mismatch.
export default defineConfig({
  esbuild: { jsx: "automatic", jsxImportSource: "react" },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});

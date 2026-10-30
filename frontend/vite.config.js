import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.js"],
    coverage: { provider: "v8", include: ["src/**"], exclude: ["src/test/**", "src/main.jsx"], reporter: ["text", "html"] },
  },
});

import { defineConfig } from "vitest/config";
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 4181,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.BOOKING_PROXY_TARGET || "http://127.0.0.1:4180",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["tests/setup.ts"],
    restoreMocks: true,
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 只代理后端 API，避免把前端的 /api-service 路由误判成 /api。
      "^/api/": "http://127.0.0.1:8000"
    }
  }
});

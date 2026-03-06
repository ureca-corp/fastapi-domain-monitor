import path from "node:path"

import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const backendOrigin = env.VITE_MONITOR_BACKEND_ORIGIN || "http://127.0.0.1:8000"
  const shouldProxyMonitor = command === "serve" && !env.VITE_MONITOR_BASE_URL

  return {
    base: command === "build" ? "/_fastapi-domain-monitor-static/" : "/",
    plugins: [
      react({
        babel: {
          plugins: ["babel-plugin-react-compiler"],
        },
      }),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "."),
      },
    },
    server: {
      host: "0.0.0.0",
      port: 3000,
      strictPort: true,
      proxy: shouldProxyMonitor
        ? {
            "/domain-monitor/api": {
              target: backendOrigin,
              changeOrigin: true,
            },
            "/domain-monitor/ws": {
              target: backendOrigin,
              changeOrigin: true,
              ws: true,
            },
          }
        : undefined,
    },
    preview: {
      host: "0.0.0.0",
      port: 4173,
      strictPort: true,
    },
    build: {
      emptyOutDir: true,
      outDir: "dist",
    },
  }
})

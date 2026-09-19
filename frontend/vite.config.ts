import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The dev server proxies /api so the app uses same-origin URLs everywhere,
    // exactly as it does behind nginx in production.
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
})

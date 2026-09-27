import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Keep browser requests same-origin in development. This avoids an
      // IPv4/IPv6 localhost mismatch and means CORS is not part of normal
      // local development.
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('/node_modules/')) return
          if (id.includes('/recharts/') || id.includes('/d3-')) return 'charts'
          if (id.includes('/react-leaflet/') || id.includes('/leaflet/')) return 'maps'
          if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react-vendor'
        },
      },
    },
  },
})

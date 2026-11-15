import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxy = { '/api': { target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } }
  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, strictPort: true, proxy },
    build: { rollupOptions: { output: { manualChunks: { charts: ['recharts'], framework: ['react', 'react-dom', 'react-router-dom'] } } } },
    test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', restoreMocks: true },
  }
})

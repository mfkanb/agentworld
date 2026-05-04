import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/drink': 'http://localhost:8000',
      '/drinks': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
      '/guestbook': 'http://localhost:8000',
      '/selfies': 'http://localhost:8000',
      '/data': 'http://localhost:8000',
    },
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // forward API calls to Django so we don't need CORS in dev
    proxy: { '/api': 'http://localhost:8000' },
  },
})

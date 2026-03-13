import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../backend/static',
    emptyOutDir: true
  },
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        ws: true
      }
    }
  }
});

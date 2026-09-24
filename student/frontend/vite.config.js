import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    hmr: { clientPort: 5174 },
    watch: { usePolling: true, interval: 1000 },
    proxy: { '/api': { target: 'http://api:8000', changeOrigin: true } },
  },
});

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Local development: this dev server is the single entry point (http://localhost:5173),
// mirroring the production reverse proxy so that sub-path routing behaves the same.
const eventpassDev = process.env.EVENTPASS_DEV_URL || 'http://127.0.0.1:5174';
const eventpassApi = process.env.EVENTPASS_API_TARGET || 'http://127.0.0.1:8000';
const sermonDev = process.env.SERMON_DEV_URL || 'http://127.0.0.1:5175';
const sermonApi = process.env.SERMON_API_TARGET || 'http://127.0.0.1:8010';

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api/eventpass': { target: eventpassApi, changeOrigin: true },
      '/eventpass': { target: eventpassDev, changeOrigin: true, ws: true },
      '/api/sermon-ai': { target: sermonApi, changeOrigin: true },
      '/sermon-ai': { target: sermonDev, changeOrigin: true, ws: true },
    },
  },
});

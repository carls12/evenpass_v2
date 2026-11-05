import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Sermon Intelligence lives under /sermon-ai/ on the CMGI Apps domain.
const base = process.env.SERMON_BASE_PATH || '/sermon-ai/';
const api = process.env.SERMON_API_TARGET || 'http://127.0.0.1:8010';

export default defineConfig({
  base,
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5175, strictPort: true, allowedHosts: ['.ngrok-free.app', '.ngrok-free.dev', '.ngrok.app', '.ngrok.dev', '.ngrok.io'], proxy: { '/api/sermon-ai': { target: api, changeOrigin: true } } },
});

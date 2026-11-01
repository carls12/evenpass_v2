import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// EventPass lives under /eventpass/ on the CMGI Apps domain (override with EVENTPASS_BASE_PATH).
const base = process.env.EVENTPASS_BASE_PATH || '/eventpass/';
const api = process.env.EVENTPASS_API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  base,
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5174, strictPort: true, proxy: { '/api/eventpass': { target: api, changeOrigin: true } } },
});

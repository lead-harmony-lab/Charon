import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'url';
import path from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    // This is the magic routing that fixes dev mode!
    proxy: {
      '/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true, // Enables WebSocket proxying
      }
    }
  },
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
  },
});
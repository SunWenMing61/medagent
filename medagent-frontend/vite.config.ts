import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 3000,
    hmr: false,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
  },
});

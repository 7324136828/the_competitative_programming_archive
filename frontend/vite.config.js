import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

function backendProxy() {
  return {
    target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:3001',
    changeOrigin: true,
    configure(proxy) {
      proxy.on('proxyReq', (proxyRequest, request) => {
        // Client-supplied forwarding headers must never grant host settings access.
        for (const name of ['x-forwarded-for', 'x-study-client-ip', 'x-study-proxy-token']) {
          proxyRequest.removeHeader(name);
        }
        proxyRequest.setHeader('X-Study-Client-IP', request.socket.remoteAddress || 'unknown');
        if (process.env.STUDY_PROXY_TOKEN) {
          proxyRequest.setHeader('X-Study-Proxy-Token', process.env.STUDY_PROXY_TOKEN);
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': backendProxy(),
      '/uploads': backendProxy(),
    },
  },
});


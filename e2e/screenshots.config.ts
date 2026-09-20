import { defineConfig } from '@playwright/test';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import base from './playwright.config';

const root = dirname(fileURLToPath(import.meta.url));
const storage = join(root, 'test-results', 'readme-storage');
const backendUrl = 'http://127.0.0.1:18001';
const frontendUrl = 'http://127.0.0.1:15174';

// Keep documentation fixtures separate from both user data and regression data.
export default defineConfig({
  ...base,
  testDir: './screenshots',
  outputDir: './test-results/readme-run',
  reporter: 'line',
  timeout: 60_000,
  retries: 0,
  use: { ...base.use, baseURL: frontendUrl, reducedMotion: 'reduce' },
  projects: base.projects?.map(project => ({
    ...project, use: { ...project.use, viewport: { width: 1600, height: 1000 } },
  })),
  webServer: (Array.isArray(base.webServer) ? base.webServer : [base.webServer!]).map((server, index) =>
    index === 0 ? {
      ...server,
      command: server.command.replace('--port 8001', '--port 18001'),
      url: `${backendUrl}/api/health`,
      env: { ...server.env, DATABASE_PATH: join(storage, 'demo.sqlite'), WORKSPACE_STORAGE_DIR: join(storage, 'files') },
    } : {
      ...server,
      command: server.command.replace('--port 5174', '--port 15174'),
      url: frontendUrl,
      env: { ...server.env, VITE_BACKEND_URL: backendUrl },
    }),
});

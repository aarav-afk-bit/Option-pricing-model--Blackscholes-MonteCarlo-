// Browser tests: starts the backend (fake NSE) and a static server for the
// frontend, then drives the dashboard in Chromium.
//   cd options-frontend/tests/e2e && npm ci && npx playwright install chromium && npx playwright test
import { defineConfig, devices } from '@playwright/test';

const python = process.env.PYTHON || 'python';

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  expect: { timeout: 20_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: { baseURL: 'http://localhost:8080', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'phone', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    { command: `${python} mock_backend.py`, url: 'http://localhost:5000/api/health', reuseExistingServer: !process.env.CI, timeout: 60_000 },
    { command: `${python} -m http.server 8080 --directory ../..`, url: 'http://localhost:8080/index.html', reuseExistingServer: !process.env.CI },
  ],
});

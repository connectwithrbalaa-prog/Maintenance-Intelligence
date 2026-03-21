const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.PORTAL_BASE_URL || 'http://127.0.0.1:8000',
    headless: true,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'python -m uvicorn maintenance_intelligence.api.main:app --host 127.0.0.1 --port 8000',
    url: 'http://127.0.0.1:8000/portal',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      MI_DEV_ALLOW_HEADERS: 'true',
    },
  },
});

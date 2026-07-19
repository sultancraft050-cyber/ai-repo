import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  reporter: process.env.CI ? "dot" : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: 'node -e "process.env.NEXT_PUBLIC_API_BASE_URL=\'https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app\'; const cp = require(\'child_process\'); cp.spawn(\'npm\', [\'run\', \'start\', \'--\', \'-p\', \'3100\'], { stdio: \'inherit\', shell: true });"',
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

import { defineConfig, devices } from "@playwright/test";

const fullStack = process.env.E2E_AUTH === "1";
export default defineConfig({
  workers: fullStack ? 1 : undefined,
  testDir: "./e2e", use: { baseURL: "http://localhost:3100" },
  webServer: {
    command: "node scripts/start.mjs",
    url: "http://localhost:3100", reuseExistingServer: false, timeout: 60000,
    env: { API_INTERNAL_URL: fullStack ? "http://127.0.0.1:18000" : "", PORT:"3100", POSTER_ALLOWED_HOSTS:"media.sunifactory.com" },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } },
  ],
});

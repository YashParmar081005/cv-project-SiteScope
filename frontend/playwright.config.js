// End-to-end tests drive the real app (FastAPI + MongoDB + computer-vision pipeline) through a real browser.
// A dedicated server on port 8001 uses the separate database "sitescope_e2e" and its own storage dir.
import { defineConfig } from "@playwright/test";
import path from "node:path";

const backend = path.resolve("../backend");
const python = process.platform === "win32" ? path.join(backend, ".venv/Scripts/python.exe") : path.join(backend, ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./e2e/global-setup.js",
  use: {
    baseURL: "http://127.0.0.1:8001",
    channel: process.env.PW_CHANNEL ?? "msedge",   // uses the installed Edge; set PW_CHANNEL=chromium elsewhere
    headless: true,
    screenshot: "only-on-failure",
    viewport: { width: 1400, height: 900 },
  },
  webServer: {
    command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
    cwd: backend,
    url: "http://127.0.0.1:8001/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      MONGO_DB: "sitescope_e2e",
      STORAGE_DIR: path.resolve("../data/e2e-storage"),
      ALLOW_REGISTRATION: "true",
      LOG_JSON: "false",
      LOG_LEVEL: "WARNING",
    },
  },
});

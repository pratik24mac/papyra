import { defineConfig } from "@playwright/test";

// End-to-end tests run against the UI in browser mock mode (no Tauri, no sidecar): they cover the
// wizard logic, validation, the email step and privacy screen. The Rust/Python chain is covered
// by the Tauri self-test and pytest.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  retries: 0,
  use: { baseURL: "http://localhost:5174", viewport: { width: 1280, height: 900 }, colorScheme: "dark" },
  webServer: { command: "npx vite --port 5174 --strictPort", port: 5174, reuseExistingServer: true, timeout: 60_000 },
  reporter: [["list"]],
});

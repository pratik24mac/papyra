import { defineConfig } from "vitest/config";

// Unit tests only; Playwright specs live in e2e/ and run with `npx playwright test`.
export default defineConfig({ test: { include: ["src/**/*.test.ts", "src/**/*.test.tsx"], exclude: ["e2e/**", "node_modules/**"] } });

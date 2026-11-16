/**
 * Commit 17: shared DB contract suite — web leg.
 * Bundles `tests/ui/db-contract/browser-entry.ts` (real `client.web` + shared
 * contract cases) into a single IIFE with Vite, serves a blank same-origin page
 * via route interception, and injects the bundle so it runs against real
 * Chromium IndexedDB. Passes only when every shared case passes — no skips.
 */
import { test, expect } from "@playwright/test";
import { build } from "vite";
import path from "node:path";
import { DB_CONTRACT_CASES } from "../../src/db/contract/dbContractCases";
import type { ContractCaseResult } from "../../src/db/contract/contractAssert";

declare global {
  interface Window {
    __dbContractResult?: { total: number; failed: number; failures: ContractCaseResult[] };
  }
}

async function bundleContractRunner(): Promise<string> {
  const rootDir = process.cwd();
  const result: unknown = await build({
    root: rootDir,
    configFile: false,
    logLevel: "error",
    define: { __DEV__: "false" },
    resolve: {
      alias: [
        { find: /^expo-constants$/, replacement: path.join(rootDir, "tests/ui/db-contract/expoConstantsStub.ts") },
        {
          find: /^@\/src\/stores\/lessonStore$/,
          replacement: path.join(rootDir, "tests/ui/db-contract/lessonStoreStub.ts"),
        },
        { find: /^@\//, replacement: `${rootDir}/` },
      ],
    },
    build: {
      write: false,
      emptyOutDir: true,
      outDir: "artifacts/playwright/db-contract-bundle",
      minify: false,
      target: "es2022",
      rollupOptions: {
        input: path.join(rootDir, "tests/ui/db-contract/browser-entry.ts"),
        output: { format: "iife", inlineDynamicImports: true, entryFileNames: "db-contract.js" },
      },
    },
  });
  // Vite build output shape differs across versions: object with `.output`
  // array, a bare array, or a watcher. Fail loudly on anything unexpected.
  const buildResults: Array<{ output?: unknown }> = Array.isArray(result)
    ? (result as Array<{ output?: unknown }>)
    : [result as { output?: unknown }];
  const code = buildResults
    .flatMap((r) => (Array.isArray(r.output) ? r.output : []))
    .map((item) => item as { type?: unknown; code?: unknown })
    .filter((item) => item.type === "chunk" && typeof item.code === "string")
    .map((item) => item.code as string)
    .join("\n");
  if (!code.trim()) {
    throw new Error("db-contract bundle produced no JS chunks");
  }
  return code;
}

async function deleteWebDb(page: import("@playwright/test").Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const req = indexedDB.deleteDatabase("harmoniq_web_v1");
        req.onsuccess = () => resolve();
        req.onerror = () => resolve();
        req.onblocked = () => resolve();
      }),
  );
}

test("@smoke db contract suite passes against client.web (IndexedDB)", async ({ page }) => {
  const code = await bundleContractRunner();

  await page.route("**/db-contract.html", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<!doctype html><html><head><meta charset='utf-8'><title>db contract</title></head><body></body></html>",
    }),
  );
  await page.goto("/db-contract.html");
  await deleteWebDb(page);
  await page.addScriptTag({ content: code });

  await page.waitForFunction(() => window.__dbContractResult !== undefined, null, { timeout: 60_000 });
  const result = await page.evaluate(() => window.__dbContractResult);
  expect(result).toBeDefined();
  expect(result!.total).toBe(DB_CONTRACT_CASES.length);
  expect(
    result!.failed,
    `db contract failures: ${result!.failures.map((f) => `${f.name}: ${f.error}`).join(" | ")}`,
  ).toBe(0);
});

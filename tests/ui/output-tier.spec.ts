import { expect, test, type Page } from "@playwright/test";

async function seedPrefs(page: Page, prefs: Record<string, string>): Promise<void> {
  await page.evaluate(async (entries) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });

    try {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction("app_prefs", "readwrite");
        const store = tx.objectStore("app_prefs");
        for (const [key, value] of Object.entries(entries)) {
          store.put({ key, value });
        }
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"));
      });
    } finally {
      db.close();
    }
  }, prefs);
}

async function readOutputTierPref(page: Page): Promise<string | null> {
  return page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });

    try {
      return await new Promise<string | null>((resolve, reject) => {
        const tx = db.transaction("app_prefs", "readonly");
        const request = tx.objectStore("app_prefs").get("output_tier");
        request.onsuccess = () => {
          const row = request.result as { value?: string } | undefined;
          resolve(typeof row?.value === "string" ? row.value : null);
        };
        request.onerror = () => reject(request.error ?? new Error("IndexedDB read failed"));
      });
    } finally {
      db.close();
    }
  });
}

test("notation complexity defaults to Intermediate and persists changes", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/settings");

  const learner = page.getByRole("button", { name: "learner", exact: true });
  const intermediate = page.getByRole("button", { name: "intermediate", exact: true });
  const transcriber = page.getByRole("button", { name: "transcriber", exact: true });

  await expect(intermediate).toBeVisible({ timeout: 15_000 });
  await expect(intermediate).toHaveClass(/border-amber-accent/);
  expect(await readOutputTierPref(page)).toBeNull();

  await learner.click();
  await expect(learner).toHaveClass(/border-amber-accent/);
  await expect(page.getByText("Notation set to learner.")).toBeVisible();
  expect(await readOutputTierPref(page)).toBe("learner");

  await page.reload();
  await expect(learner).toBeVisible({ timeout: 15_000 });
  await expect(learner).toHaveClass(/border-amber-accent/);

  await transcriber.click();
  await expect(transcriber).toHaveClass(/border-amber-accent/);
  await expect
    .poll(async () => readOutputTierPref(page))
    .toBe("transcriber");

  await intermediate.click();
  await expect
    .poll(async () => readOutputTierPref(page))
    .toBe("intermediate");
});

test("Learner tier shows the simplified Study view without theory", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/settings");
  await page.getByRole("button", { name: "learner", exact: true }).click();
  await expect(page.getByRole("button", { name: "learner", exact: true })).toHaveClass(
    /border-amber-accent/,
  );
  await seedPrefs(page, {
    onboarding_complete: "1",
    mood_check_skip: "1",
    session_skip_tune: "1",
  });

  await page.goto("/");
  const demo = page.getByRole("button", { name: "Play demo session" });
  await expect(demo).toBeVisible({ timeout: 20_000 });
  await demo.click();
  await expect(page).toHaveURL(/\/session\/musical-tolerance/, { timeout: 30_000 });

  await page.getByRole("button", { name: "Select mode Expressive" }).click();
  await expect(page).toHaveURL(/\/session\/study/, { timeout: 30_000 });
  await expect(page.getByText("Chord chart")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Solo melody")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Theory:/ })).toHaveCount(0);
});

test("Transcriber tier exposes Print and MusicXML export in Study", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/settings");
  await page.getByRole("button", { name: "transcriber", exact: true }).click();
  await expect(page.getByRole("button", { name: "transcriber", exact: true })).toHaveClass(
    /border-amber-accent/,
  );
  await seedPrefs(page, {
    onboarding_complete: "1",
    mood_check_skip: "1",
    session_skip_tune: "1",
  });

  await page.goto("/");
  const demo = page.getByRole("button", { name: "Play demo session" });
  await expect(demo).toBeVisible({ timeout: 20_000 });
  await demo.click();
  await expect(page).toHaveURL(/\/session\/musical-tolerance/, { timeout: 30_000 });

  await page.getByRole("button", { name: "Select mode Expressive" }).click();
  await expect(page).toHaveURL(/\/session\/study/, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Print the current score" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByRole("button", { name: "Export MusicXML for the current section" }),
  ).toBeVisible();
});

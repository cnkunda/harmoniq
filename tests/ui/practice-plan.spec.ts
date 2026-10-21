import { expect, test, type Page } from "@playwright/test";

const ACTIVE_PLAN = {
  plan_id: "e2e-active-plan",
  total_duration_seconds: 1500,
  slots: [
    {
      slot_id: "e2e-slot-warmup",
      slot_type: "warmup",
      duration_seconds: 600,
      title: "Warm-up",
      coach_intro: "Loosen up slowly.",
      difficulty: 1,
      intent: "practice",
    },
    {
      slot_id: "e2e-slot-jam",
      slot_type: "free_jam",
      duration_seconds: 900,
      title: "Free jam",
      coach_intro: "Play over the changes.",
      difficulty: 2,
      intent: "practice",
    },
  ],
};

const ACTIVE_ROW = {
  plan_id: ACTIVE_PLAN.plan_id,
  status: "active",
  current_slot_index: 1,
  plan_json: JSON.stringify(ACTIVE_PLAN),
  slot_results_json: JSON.stringify([
    {
      slot_id: "e2e-slot-warmup",
      slot_type: "warmup",
      title: "Warm-up",
      accuracy: 0.81,
      timing: 0.76,
      confidence: "high",
      completion: true,
      completed_at: "2026-10-21T09:00:00.000Z",
    },
  ]),
  adaptation_log: "[]",
  started_at: "2026-10-21T08:45:00.000Z",
  updated_at: "2026-10-21T09:00:00.000Z",
};

const COMPLETION_ROW = {
  id: "e2e-completion",
  completed_at: "2026-10-21T09:30:00.000Z",
  plan_json: JSON.stringify({
    plan_id: "e2e-completed-plan",
    total_duration_seconds: 1200,
    slots: [
      {
        slot_id: "e2e-done-warmup",
        slot_type: "warmup",
        duration_seconds: 600,
        title: "Warm-up",
        coach_intro: "",
        difficulty: 1,
        intent: "practice",
      },
      {
        slot_id: "e2e-done-remediation",
        slot_type: "technique",
        duration_seconds: 600,
        title: "Remediation — Bending",
        coach_intro: "",
        difficulty: 1,
        intent: "remediation",
      },
    ],
    slot_results: [
      {
        slot_id: "e2e-done-warmup",
        slot_type: "warmup",
        title: "Warm-up",
        accuracy: 0.82,
        timing: 0.74,
        confidence: "high",
        completion: true,
        completed_at: "2026-10-21T09:30:00.000Z",
      },
      {
        slot_id: "e2e-done-remediation",
        slot_type: "technique",
        title: "Remediation — Bending",
        accuracy: null,
        timing: null,
        confidence: null,
        completion: true,
        completed_at: "2026-10-21T09:31:00.000Z",
      },
    ],
    adaptation_log: [
      { slot_id: "e2e-done-warmup", action: "insert_remediation", reason: "low" },
      { slot_id: "e2e-done-remediation", action: "skip_easier", reason: "high" },
    ],
  }),
};

async function seedPlanRow(page: Page, store: string, row: object): Promise<void> {
  await page.evaluate(
    async ({ storeName, rowValue }) => {
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open("harmoniq_web_v1");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
      });
      if (!db.objectStoreNames.contains(storeName)) {
        db.close();
        throw new Error(`${storeName} store is not initialized`);
      }
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(storeName, "readwrite");
        const store = tx.objectStore(storeName);
        store.clear();
        store.put(rowValue);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"));
        tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
      });
      db.close();
    },
    { storeName: store, rowValue: row },
  );
}

test("home resumes an active practice plan", async ({ page }) => {
  test.setTimeout(90_000);

  await page.goto("/");
  await expect(page.getByText("First time here")).toBeVisible({ timeout: 30_000 });
  await seedPlanRow(page, "app_prefs", { key: "onboarding_complete", value: "1" });
  await seedPlanRow(page, "practice_plans", ACTIVE_ROW);
  await page.goto("/");

  await expect(page.getByText("Resume your 25-min session")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Step 2 of 2 · pick up where you left off")).toBeVisible();
  await expect(page.getByRole("button", { name: /Resume today's practice session/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Regenerate practice plan/ })).toHaveCount(0);
});

test("regenerate produces an updated home preview plan", async ({ page }) => {
  test.setTimeout(90_000);
  let regenerated = false;
  let planRequests = 0;

  await page.route("**/practice/plan", async (route) => {
    planRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        plan_id: regenerated ? "preview-regenerated" : "preview-initial",
        total_duration_seconds: 1500,
        slots: [
          {
            slot_id: "preview-slot",
            slot_type: "song_section",
            duration_seconds: 1500,
            title: regenerated ? "Plan beta" : "Plan alpha",
            coach_intro: "Preview slot.",
            difficulty: 3,
            intent: "practice",
          },
        ],
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByText("First time here")).toBeVisible({ timeout: 30_000 });
  await seedPlanRow(page, "app_prefs", { key: "onboarding_complete", value: "1" });
  await seedPlanRow(page, "lesson_cache", {
    id: "latest",
    savedAt: "2026-10-21T09:00:00.000Z",
    lesson: {
      job_id: "job-preview",
      song_title: "Preview Song",
      artist: "Tester",
      sections: [{ label: "Intro" }],
    },
  });
  await page.goto("/");

  await expect(page.getByText("Plan alpha").first()).toBeVisible({ timeout: 30_000 });
  const beforeRegenerate = planRequests;
  regenerated = true;
  await page.getByRole("button", { name: "Regenerate practice plan" }).click();

  await expect(page.getByText("Plan beta").first()).toBeVisible({ timeout: 30_000 });
  expect(planRequests).toBeGreaterThan(beforeRegenerate);
});

test("progress lists per-slot scores for completed plans", async ({ page }) => {
  test.setTimeout(90_000);

  await page.goto("/progress");
  await expect(page.getByText("No history yet")).toBeVisible({ timeout: 30_000 });
  await seedPlanRow(page, "practice_plan_completions", COMPLETION_ROW);
  await page.reload();

  await expect(page.getByText("Practice plan completed")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/1 remediation · 1 skipped/)).toBeVisible();
  await expect(page.getByText("82% pitch")).toBeVisible();
  await expect(page.getByText("74% timing")).toBeVisible();
  await expect(page.getByText("Done", { exact: true })).toBeVisible();
});

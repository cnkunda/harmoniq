import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

type AnalyticsSeed = {
  id: string;
  user_id: string;
  event_type: string;
  payload_json: string;
  timestamp: string;
};

type FeedbackSeed = {
  id: string;
  job_id: string;
  song_id: string;
  user_id: string;
  timestamp: string;
  feedback_type: "chord_correction" | "note_correction" | "wrong_chord";
  event_index: number;
  original_value: string;
  corrected_value: string | null;
  reason: string | null;
};

async function expectTouchTarget(locator: Locator, label: string): Promise<void> {
  const box = await locator.boundingBox();
  expect(box, `${label} should render`).not.toBeNull();
  expect(Math.round(box!.height), `${label} height`).toBeGreaterThanOrEqual(44);
  expect(Math.round(box!.width), `${label} width`).toBeGreaterThanOrEqual(44);
}

async function openSettings(page: Page): Promise<void> {
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Open practice insights" })).toBeVisible({
    timeout: 15_000,
  });
}

async function seedAnalytics(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });

    if (
      !db.objectStoreNames.contains("analytics_events") ||
      !db.objectStoreNames.contains("user_feedback")
    ) {
      db.close();
      throw new Error("Harmoniq analytics stores are not initialized");
    }

    const now = Date.now();
    const iso = (minutesAgo: number): string => new Date(now - minutesAgo * 60_000).toISOString();
    const analytics: AnalyticsSeed[] = [
      {
        id: "analytics-start-1",
        user_id: "seed-user",
        event_type: "session_start",
        payload_json: JSON.stringify({ song_title: "Gravity", step: "tune" }),
        timestamp: iso(180),
      },
      {
        id: "analytics-complete-1",
        user_id: "seed-user",
        event_type: "session_complete",
        payload_json: JSON.stringify({
          song_title: "Gravity",
          duration_sec: 300,
          final_step: "review",
          started_at: iso(180),
        }),
        timestamp: iso(175),
      },
      {
        id: "analytics-start-2",
        user_id: "seed-user",
        event_type: "session_start",
        payload_json: JSON.stringify({ song_title: "Gravity", step: "tune" }),
        timestamp: iso(120),
      },
      {
        id: "analytics-play-along",
        user_id: "seed-user",
        event_type: "play_along_complete",
        payload_json: JSON.stringify({ duration_sec: 40, tempo_bpm: 90, reason: "done" }),
        timestamp: iso(90),
      },
      {
        id: "analytics-start-3",
        user_id: "seed-user",
        event_type: "session_start",
        payload_json: JSON.stringify({ song_title: "Neon", step: "tune" }),
        timestamp: iso(60),
      },
      {
        id: "analytics-complete-2",
        user_id: "seed-user",
        event_type: "session_complete",
        payload_json: JSON.stringify({
          song_title: "Neon",
          duration_sec: 120,
          final_step: "review",
          started_at: iso(60),
        }),
        timestamp: iso(55),
      },
    ];

    const feedback: FeedbackSeed[] = [
      {
        id: "analytics-feedback-1",
        job_id: "insights-job",
        song_id: "insights-song",
        user_id: "seed-user",
        timestamp: iso(5),
        feedback_type: "chord_correction",
        event_index: 0,
        original_value: JSON.stringify({ chord: "G" }),
        corrected_value: JSON.stringify({ chord: "Gmaj7" }),
        reason: null,
      },
    ];

    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(["analytics_events", "user_feedback"], "readwrite");
      const analyticsStore = tx.objectStore("analytics_events");
      analyticsStore.clear();
      for (const row of analytics) analyticsStore.put(row);
      const feedbackStore = tx.objectStore("user_feedback");
      feedbackStore.clear();
      for (const row of feedback) feedbackStore.put(row);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"));
      tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
    });

    db.close();
  });
}

async function readAnalyticsOptOut(page: Page): Promise<string | null> {
  return page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });
    const value = await new Promise<string | null>((resolve, reject) => {
      const tx = db.transaction("app_prefs", "readonly");
      const request = tx.objectStore("app_prefs").get("analytics_opt_out");
      request.onsuccess = () => {
        const row = request.result as { key: string; value: string } | undefined;
        resolve(row?.value ?? null);
      };
      request.onerror = () => reject(request.error ?? new Error("IndexedDB read failed"));
    });
    db.close();
    return value;
  });
}

test("privacy settings expose insights, a persisted opt-out toggle, and empty export state", async ({
  page,
}) => {
  await openSettings(page);

  const optOutSwitch = page.getByRole("switch", { name: "Share practice data" });
  await expect(optOutSwitch).toBeVisible();
  await expect(optOutSwitch).toBeChecked();
  await expectTouchTarget(optOutSwitch, "analytics opt-out switch");

  const insightsEntry = page.getByRole("button", { name: "Open practice insights" });
  await expectTouchTarget(insightsEntry, "practice insights entry");

  const exportButton = page.getByRole("button", { name: "Export my data" });
  await expect(exportButton).toBeDisabled();
  await expect(page.getByText(/No local analytics events yet/)).toBeVisible();

  await optOutSwitch.click();
  await expect(optOutSwitch).not.toBeChecked();
  await expect.poll(() => readAnalyticsOptOut(page)).toBe("1");

  await page.reload();
  const reloadedSwitch = page.getByRole("switch", { name: "Share practice data" });
  await expect(reloadedSwitch).toBeVisible({ timeout: 15_000 });
  await expect(reloadedSwitch).not.toBeChecked();

  await reloadedSwitch.click();
  await expect(reloadedSwitch).toBeChecked();
  await expect.poll(() => readAnalyticsOptOut(page)).toBe("0");
});

test("practice insights summarizes local events and exports CSV", async ({ page }) => {
  await openSettings(page);
  await seedAnalytics(page);
  await page.reload();

  const insightsEntry = page.getByRole("button", { name: "Open practice insights" });
  await expect(insightsEntry).toBeVisible({ timeout: 15_000 });
  await insightsEntry.click();
  await expect(page).toHaveURL(/\/settings\/analytics$/);

  await expect(page.getByText("Anonymous patterns from this device only.")).toBeVisible();
  await expect(page.getByLabel("Sessions: 3")).toBeVisible();
  await expect(page.getByLabel("Completed: 2")).toBeVisible();
  await expect(page.getByLabel("Completion: 67%")).toBeVisible();
  await expect(page.getByText("3m 30s", { exact: true })).toBeVisible();
  await expect(page.getByText("40s", { exact: true })).toBeVisible();
  await expect(page.getByText("Gravity", { exact: true })).toBeVisible();
  await expect(page.getByText("2 sessions", { exact: true })).toBeVisible();
  await expect(page.getByText("Gmaj7", { exact: true })).toBeVisible();

  await expectTouchTarget(page.getByRole("button", { name: "Back to settings" }), "back");
  await page.getByRole("button", { name: "Back to settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);

  const exportButton = page.getByRole("button", { name: "Export my data" });
  await expect(exportButton).toBeEnabled();
  await expectTouchTarget(exportButton, "export my data");

  const downloadPromise = page.waitForEvent("download");
  await exportButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^harmoniq-analytics-\d{4}-\d{2}-\d{2}\.csv$/);

  const filePath = await download.path();
  expect(filePath, "download path").not.toBeNull();
  const csv = readFileSync(filePath!, "utf8");
  const lines = csv.split("\r\n");
  expect(lines[0]).toBe("id,user_id,event_type,timestamp,payload_json");
  expect(lines.some((line) => line.startsWith("analytics-start-1,seed-user,session_start,"))).toBe(
    true,
  );
  expect(csv).toContain("Gravity");
  expect(csv).toContain("feature_usage");
});

test("onboarding shows the analytics notice", async ({ page }) => {
  await page.goto("/onboarding");
  await expect(
    page.getByText("We track practice patterns to improve your experience. Opt out anytime."),
  ).toBeVisible({ timeout: 15_000 });
});

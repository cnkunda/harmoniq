import { readFileSync } from "node:fs";

import { expect, test, type Download, type Locator, type Page } from "@playwright/test";

const DEMO_JOB_ID = "harmoniq-demo-lesson-v1";
const SERVER_JOB_ID = "server-feedback-job";

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

const DEMO_LESSON = {
  job_id: DEMO_JOB_ID,
  song_title: "Feedback fixture",
  artist: "Harmoniq",
  key: "G major",
  tempo: 90,
  bar_timestamps: [0, 2.666, 5.333, 8],
  chord_timeline: {
    events: [
      { timestamp: 0, chord: "G", confidence: 0.92 },
      { timestamp: 2.666, chord: "C", confidence: 0.9 },
      { timestamp: 5.333, chord: "D", confidence: 0.88 },
    ],
  },
  solo_notes: {
    notes: [{ start_time: 0.5, duration: 0.3, pitch: 67, velocity: 80 }],
  },
  sections: [{ label: "Main", start_time_seconds: 0, confidence: 0.9 }],
};

function demoRows(): FeedbackSeed[] {
  return [
    {
      id: "feedback-chord-1",
      job_id: DEMO_JOB_ID,
      song_id: "demo-song",
      user_id: "test-user",
      timestamp: "2026-10-20T10:00:01.000Z",
      feedback_type: "chord_correction",
      event_index: 0,
      original_value: JSON.stringify({ chord: "G" }),
      corrected_value: JSON.stringify({ chord: "Gmaj7" }),
      reason: "bridge voicing",
    },
    {
      id: "feedback-wrong-2",
      job_id: DEMO_JOB_ID,
      song_id: "demo-song",
      user_id: "test-user",
      timestamp: "2026-10-20T10:00:02.000Z",
      feedback_type: "wrong_chord",
      event_index: 1,
      original_value: JSON.stringify({ chord: "C" }),
      corrected_value: null,
      reason: null,
    },
    {
      id: "feedback-note-3",
      job_id: DEMO_JOB_ID,
      song_id: "demo-song",
      user_id: "test-user",
      timestamp: "2026-10-20T10:00:03.000Z",
      feedback_type: "note_correction",
      event_index: 2,
      original_value: JSON.stringify({ pitch: 64 }),
      corrected_value: JSON.stringify({ pitch: 65 }),
      reason: null,
    },
  ];
}

function serverRow(): FeedbackSeed {
  return {
    id: "feedback-server-1",
    job_id: SERVER_JOB_ID,
    song_id: "server-song",
    user_id: "test-user",
    timestamp: "2026-10-20T11:00:00.000Z",
    feedback_type: "chord_correction",
    event_index: 0,
    original_value: JSON.stringify({ chord: "Am" }),
    corrected_value: JSON.stringify({ chord: "Am7" }),
    reason: null,
  };
}

async function openFeedbackPage(page: Page, seed: FeedbackSeed[] = []): Promise<void> {
  await page.goto("/settings/feedback");
  await expect(page.getByText("No feedback yet")).toBeVisible({ timeout: 15_000 });
  if (seed.length === 0) return;
  await seedIndexedDb(page, { feedback: seed });
  await page.reload();
  await expect(page.getByText(seed[0]!.job_id)).toBeVisible({ timeout: 15_000 });
}

async function seedIndexedDb(
  page: Page,
  seed: { feedback?: FeedbackSeed[]; lesson?: Record<string, unknown> },
): Promise<void> {
  await page.evaluate(async ({ feedback, lesson }) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });

    if (!db.objectStoreNames.contains("user_feedback") || !db.objectStoreNames.contains("lesson_cache")) {
      db.close();
      throw new Error("Harmoniq IndexedDB stores are not initialized");
    }

    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(["user_feedback", "lesson_cache"], "readwrite");
      const feedbackStore = tx.objectStore("user_feedback");
      feedbackStore.clear();
      for (const row of feedback ?? []) feedbackStore.put(row);
      const lessonStore = tx.objectStore("lesson_cache");
      lessonStore.clear();
      if (lesson) {
        lessonStore.put({ id: "latest", lesson, savedAt: new Date().toISOString() });
      }
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"));
      tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
    });

    db.close();
  }, seed);
}

async function readFeedbackRows(page: Page): Promise<FeedbackSeed[]> {
  return page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });
    const rows = await new Promise<FeedbackSeed[]>((resolve, reject) => {
      const tx = db.transaction("user_feedback", "readonly");
      const request = tx.objectStore("user_feedback").getAll();
      request.onsuccess = () => resolve(request.result as FeedbackSeed[]);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB read failed"));
    });
    db.close();
    return rows;
  });
}

async function expectTouchTarget(locator: Locator, label: string): Promise<void> {
  const box = await locator.boundingBox();
  expect(box, `${label} should render`).not.toBeNull();
  expect(Math.round(box!.height), `${label} height`).toBeGreaterThanOrEqual(44);
  expect(Math.round(box!.width), `${label} width`).toBeGreaterThanOrEqual(44);
}

async function readDownloadJson(download: Download): Promise<Record<string, unknown>> {
  const filePath = await download.path();
  expect(filePath, "download path").not.toBeNull();
  return JSON.parse(readFileSync(filePath!, "utf8")) as Record<string, unknown>;
}

test("settings exposes both feedback entry points and back navigation", async ({ page }) => {
  await page.goto("/settings");

  const topEntry = page.getByRole("button", { name: "Open feedback and corrections" });
  await expect(topEntry).toBeVisible({ timeout: 15_000 });
  await expectTouchTarget(topEntry, "top feedback entry");
  await topEntry.click();
  await expect(page).toHaveURL(/\/settings\/feedback$/);
  await expect(page.getByText("Feedback", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Back to settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);

  await page.getByRole("button", { name: /Data Management, (collapsed|expanded)/ }).click();
  const dataManagementEntry = page.getByRole("button", {
    name: "Open feedback and correction history",
  });
  await expect(dataManagementEntry).toBeVisible();
  await expectTouchTarget(dataManagementEntry, "data-management feedback entry");
  await dataManagementEntry.click();
  await expect(page).toHaveURL(/\/settings\/feedback$/);
});

test("empty feedback state disables exports and keeps touch targets", async ({ page }) => {
  await openFeedbackPage(page);

  await expect(page.getByText("No feedback yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Export all chord feedback" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Export all solo feedback" })).toBeDisabled();
  await expectTouchTarget(page.getByRole("button", { name: "Back to settings" }), "back");
  await expectTouchTarget(
    page.getByRole("button", { name: "Export all chord feedback" }),
    "export all chords",
  );
});

test("populated feedback dashboard summarizes rows and keeps touch targets", async ({ page }) => {
  await openFeedbackPage(page, demoRows());

  await expect(page.getByText("Most corrected chords")).toBeVisible();
  await expect(page.getByText("Gmaj7 (1)")).toBeVisible();
  await expect(page.getByText(/3 reports · 1 chord · 1 note · 1 flagged/)).toBeVisible();
  await expect(page.getByText("Chord correction · event 1")).toBeVisible();
  await expect(page.getByText("Wrong chord · event 2")).toBeVisible();
  await expect(page.getByText("Note correction · event 3")).toBeVisible();

  await expectTouchTarget(
    page.getByRole("button", { name: "Export all chord feedback" }),
    "export all chords",
  );
  await expectTouchTarget(
    page.getByRole("button", { name: `Export chord feedback for ${DEMO_JOB_ID}` }),
    "job chord export",
  );
  await expectTouchTarget(
    page.getByRole("button", { name: "Revert Chord correction for event 1" }),
    "revert",
  );
});

test("revert removes a demo-job feedback row without server sync", async ({ page }) => {
  await openFeedbackPage(page, demoRows());

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Revert this feedback?");
    await dialog.accept();
  });

  await page.getByRole("button", { name: "Revert Wrong chord for event 2" }).click();
  await expect(page.getByText("Feedback reverted")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText("Wrong chord · event 2")).toHaveCount(0);
  await expect(page.getByText(/2 reports · 1 chord · 1 note · 0 flagged/)).toBeVisible();
});

test("exports all chord and job solo feedback as JSON", async ({ page }) => {
  await openFeedbackPage(page, demoRows());

  const allChordDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export all chord feedback" }).click();
  const allChordDownload = await allChordDownloadPromise;
  expect(allChordDownload.suggestedFilename()).toBe("chord_feedback.json");
  const allChord = await readDownloadJson(allChordDownload);
  expect(allChord.job_id).toBe("all");
  expect(allChord.split).toBe("chord");
  expect(allChord.user_id).toBeTruthy();
  expect(allChord.records).toHaveLength(2);

  const jobSoloDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: `Export solo feedback for ${DEMO_JOB_ID}` }).click();
  const jobSoloDownload = await jobSoloDownloadPromise;
  expect(jobSoloDownload.suggestedFilename()).toBe(`solo_feedback_${DEMO_JOB_ID}.json`);
  const jobSolo = await readDownloadJson(jobSoloDownload);
  expect(jobSolo.job_id).toBe(DEMO_JOB_ID);
  expect(jobSolo.split).toBe("solo");
  expect(jobSolo.records).toHaveLength(1);
});

test("server export failure falls back to local JSON", async ({ page }) => {
  await page.route("**/analyze/**/feedback/export*", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "export unavailable" }),
    }),
  );
  await openFeedbackPage(page, [serverRow()]);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: `Export chord feedback for ${SERVER_JOB_ID}` }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`chord_feedback_${SERVER_JOB_ID}.json`);
  const payload = await readDownloadJson(download);
  expect(payload.job_id).toBe(SERVER_JOB_ID);
  expect(payload.records).toHaveLength(1);
  await expect(page.getByText(/Server export unavailable/)).toBeVisible({ timeout: 5_000 });
});

test("Report incorrect writes a demo feedback row", async ({ page }) => {
  await page.route("**/session/orient-clip", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }),
  );

  await page.goto("/session/listen");
  await expect(page.getByText("No song loaded for the Listen step")).toBeVisible({ timeout: 15_000 });
  await seedIndexedDb(page, { lesson: DEMO_LESSON });
  await page.reload();

  const chord = page.getByRole("button", { name: "Chord G at bar 1" });
  await expect(chord).toBeVisible({ timeout: 20_000 });
  await chord.click();
  await expect(page.getByText("Correct Chord")).toBeVisible();
  await page.getByRole("button", { name: "Report this chord as incorrect" }).click();
  await expect(page.getByText("Feedback saved on this device")).toBeVisible({ timeout: 5_000 });

  await expect
    .poll(async () => {
      const rows = await readFeedbackRows(page);
      return rows.some(
        (row) =>
          row.job_id === DEMO_JOB_ID &&
          row.feedback_type === "wrong_chord" &&
          row.event_index === 0,
      );
    })
    .toBe(true);

  const row = (await readFeedbackRows(page)).find(
    (candidate) =>
      candidate.job_id === DEMO_JOB_ID &&
      candidate.feedback_type === "wrong_chord" &&
      candidate.event_index === 0,
  );
  expect(row?.original_value).toBe(JSON.stringify({ chord: "G" }));
  expect(row?.corrected_value).toBeNull();
});

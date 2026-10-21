import { expect, test, type Page } from "@playwright/test";

const SUMMARY_BUNDLE = {
  chord: "A minor pentatonic",
  clarity: 0.82,
  intonation_cents: { mean_abs: 12 },
  timing_ms: 0,
  transition_from: null,
  transition_gap_ms: 0,
  grade: "B",
  grade_score: 84,
  grade_breakdown: { intonation: 88, timing: 80 },
  phrase_feedback: [
    {
      phrase_index: 0,
      chord: "A minor pentatonic",
      clarity: 0.78,
      intonation_cents: 12,
      timing_ms: 0,
      transition_from: null,
      transition_gap_ms: 0,
      suggestion: "Aim for cleaner bends on the third phrase.",
    },
  ],
  weakest_phrase_index: 0,
  phrase_count: 1,
  total_notes: 4,
  avg_notes_per_second: 2,
  dominant_contour: "rising",
  pitch_class_distribution: { A: 3, C: 1 },
  vocabulary_patterns: [],
  vocabulary_diversity: 0.5,
  coach_summary: "Solid groove. Keep the bends relaxed.",
  coach_strengths: ["Steady pulse"],
  coach_focus_areas: ["Bend accuracy"],
  coach_next_step: "Loop phrase one at 0.75×.",
  persona: "learner",
  duration_seconds: 42,
  inferred_scale_label: "A minor pentatonic",
  inference_confidence: "high",
};

const JAM_ROW = {
  id: "jam-history-fixture",
  date: "2026-10-20T10:00:00.000Z",
  duration_seconds: 42,
  scale_position_map: { pc_A: 1 },
  pitch_class_weight_map: { pc_A: 1 },
  position_weight_map: {},
  inferred_scale_label: "A minor pentatonic",
  inferred_mode: "minor_pentatonic",
  inference_confidence: "high",
  track_id: "am-blues-70",
  track_label: "A minor — slow blues shuffle",
  track_key: "A minor",
  track_bpm: 70,
  reliability_tags: [],
  reliability_confidence: "high",
  reliability_signal_quality: 0.9,
  recurring_gestures: [],
  coach_summary: "Fallback summary.",
  summary_bundle_json: JSON.stringify(SUMMARY_BUNDLE),
  phrases_json: JSON.stringify([
    {
      duration_ms: 1000,
      notes_per_second: 2,
      unique_pitch_classes: 3,
      midi_span: 5,
      contour: "rising",
      note_count: 4,
      intonation_cents: 12,
      start_ms: 0,
      end_ms: 1000,
      backing_start_ms: 1000,
      backing_end_ms: 2000,
    },
  ]),
  summary_status: "ready",
};

async function seedJamSnapshot(page: Page): Promise<void> {
  await page.evaluate(async (row) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });
    if (!db.objectStoreNames.contains("jam_snapshots")) {
      db.close();
      throw new Error("jam_snapshots store is not initialized");
    }
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("jam_snapshots", "readwrite");
      const store = tx.objectStore("jam_snapshots");
      store.clear();
      store.put(row);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"));
      tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
    });
    db.close();
  }, JAM_ROW);
}

test("jam history lists saved snapshots and opens the summary", async ({ page }) => {
  test.setTimeout(60_000);

  await page.goto("/jam/history");
  await expect(page.getByText("No jams yet")).toBeVisible({ timeout: 15_000 });

  await seedJamSnapshot(page);
  await page.reload();

  const jamCard = page.getByRole("button", { name: /Open jam from/ });
  await expect(jamCard).toBeVisible({ timeout: 15_000 });
  await expect(jamCard.getByText("Summary ready")).toBeVisible();
  await expect(jamCard.getByText("B", { exact: true })).toBeVisible();

  await jamCard.click();

  await expect(page.getByText("Jam summary")).toBeVisible();
  await expect(page.getByText("Solid groove. Keep the bends relaxed.")).toBeVisible();
  await expect(page.getByText("Aim for cleaner bends on the third phrase.")).toBeVisible();
  await expect(page.getByText("Practice this phrase · 0.75×")).toBeVisible();

  await page.getByRole("button", { name: /Practice weakest phrase/ }).click();
  await expect(page).toHaveURL(/\/jam-practice\?/);
  await expect(page.getByText("Practice phrase", { exact: true })).toBeVisible();
  await expect(page.getByText(/0\.75× speed/)).toBeVisible();
});

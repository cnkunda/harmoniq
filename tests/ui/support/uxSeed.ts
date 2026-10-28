import type { Page } from "@playwright/test";

const NOW = "2026-10-27T16:00:00.000Z";
const JOB_ID = "ux-audit-lesson-v1";

const LESSON = {
  job_id: JOB_ID,
  song_title: "Midnight Blues",
  artist: "Harmoniq Studio",
  style_label: "blues",
  key: "A minor",
  key_confidence: 0.93,
  tempo: 84,
  tempo_confidence: 0.91,
  transcription_confidence: 0.82,
  analysis_audio_role: "guitar_stem",
  beat_grid: [0, 0.714, 1.428, 2.142, 2.856, 3.57, 4.284, 4.998],
  bar_timestamps: [0, 2.856, 5.712, 8.568],
  chord_timeline: {
    events: [
      { timestamp: 0, chord: "Am", confidence: 0.94 },
      { timestamp: 2.856, chord: "Dm", confidence: 0.9 },
      { timestamp: 5.712, chord: "Am", confidence: 0.92 },
      { timestamp: 8.568, chord: "E7", confidence: 0.87 },
    ],
  },
  solo_notes: {
    notes: [
      { start_time: 0.4, duration: 0.3, pitch: 69, velocity: 84 },
      { start_time: 0.9, duration: 0.25, pitch: 72, velocity: 80 },
      { start_time: 1.4, duration: 0.4, pitch: 76, velocity: 88 },
      { start_time: 2.2, duration: 0.3, pitch: 74, velocity: 82 },
      { start_time: 3.1, duration: 0.35, pitch: 72, velocity: 78 },
      { start_time: 4.0, duration: 0.5, pitch: 69, velocity: 90 },
    ],
  },
  sections: [
    {
      label: "Intro",
      start_time_seconds: 0,
      confidence: 0.91,
      coach_note: "Let the first phrase breathe — leave space between the pickups.",
      coach_explanation: "The space makes the Am-to-Dm move feel intentional instead of rushed.",
    },
    {
      label: "Verse",
      start_time_seconds: 8.568,
      confidence: 0.86,
      coach_note: "Aim for an even attack as the phrase climbs toward the E7.",
      coach_explanation: "Keep the pick angle consistent so the dynamic lift comes from the line, not volume.",
    },
  ],
  stems: {},
  lyrics_aligned: [],
};

const LESSON_ROW = {
  job_id: JOB_ID,
  lesson_json: JSON.stringify(LESSON),
  song_title: LESSON.song_title,
  artist: LESSON.artist,
  analyzed_at: "2026-10-26T18:30:00.000Z",
  section_count: LESSON.sections.length,
};

const SESSIONS = [
  {
    id: "demo-session",
    song_title: LESSON.song_title,
    artist: LESSON.artist,
    section_label: "Intro",
    date: "2026-10-26T19:10:00.000Z",
    coach_review: "Strong pocket in the first phrase. Keep the bends relaxed as you move to the verse.",
    pitch_accuracy: 0.78,
    phrasing_score: 0.74,
    nodes_targeted: ["timing", "phrasing"],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
    review_snapshot: null,
    job_id: JOB_ID,
    section_index: 0,
    is_ghost_reference: false,
    ghost_anchor_sec: null,
    ghost_audio_base64: null,
    ghost_recording_mime: null,
    mood: "focused",
  },
  {
    id: "ux-session-1",
    song_title: LESSON.song_title,
    artist: LESSON.artist,
    section_label: "Intro",
    date: "2026-10-26T19:10:00.000Z",
    coach_review: "Strong pocket in the first phrase. Keep the bends relaxed as you move to the verse.",
    pitch_accuracy: 0.78,
    phrasing_score: 0.74,
    nodes_targeted: ["timing", "phrasing"],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
    review_snapshot: null,
    job_id: JOB_ID,
    section_index: 0,
    is_ghost_reference: false,
    ghost_anchor_sec: null,
    ghost_audio_base64: null,
    ghost_recording_mime: null,
    mood: "focused",
  },
  {
    id: "ux-session-2",
    song_title: LESSON.song_title,
    artist: LESSON.artist,
    section_label: "Verse",
    date: "2026-10-25T17:45:00.000Z",
    coach_review: "Timing settled once you stopped rushing the pickup notes.",
    pitch_accuracy: 0.71,
    phrasing_score: 0.69,
    nodes_targeted: ["pitch_accuracy", "timing"],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
    review_snapshot: null,
    job_id: JOB_ID,
    section_index: 1,
    is_ghost_reference: false,
    ghost_anchor_sec: null,
    ghost_audio_base64: null,
    ghost_recording_mime: null,
    mood: "loose",
  },
];

const SKILL_NODES = [
  {
    id: "pitch_accuracy",
    label: "Pitch accuracy",
    score: 0.72,
    sessions_count: 4,
    last_session_date: "2026-10-26T19:10:00.000Z",
    easiness_factor: 2.5,
    interval_days: 3,
    next_review_date: "2026-10-29T19:10:00.000Z",
    sm2_repetitions: 2,
    technique_roll_json: "[0.69,0.73,0.72]",
    schema_version: 1,
  },
  {
    id: "phrasing",
    label: "Phrasing",
    score: 0.68,
    sessions_count: 3,
    last_session_date: "2026-10-26T19:10:00.000Z",
    easiness_factor: 2.4,
    interval_days: 2,
    next_review_date: "2026-10-28T19:10:00.000Z",
    sm2_repetitions: 1,
    technique_roll_json: "[0.64,0.7,0.68]",
    schema_version: 1,
  },
  {
    id: "timing",
    label: "Timing",
    score: 0.81,
    sessions_count: 5,
    last_session_date: "2026-10-26T19:10:00.000Z",
    easiness_factor: 2.6,
    interval_days: 4,
    next_review_date: "2026-10-30T19:10:00.000Z",
    sm2_repetitions: 3,
    technique_roll_json: "[0.78,0.82,0.81]",
    schema_version: 1,
  },
  {
    id: "bend_accuracy",
    label: "Bend accuracy",
    score: 0.59,
    sessions_count: 2,
    last_session_date: "2026-10-25T17:45:00.000Z",
    easiness_factor: 2.2,
    interval_days: 1,
    next_review_date: "2026-10-27T17:45:00.000Z",
    sm2_repetitions: 0,
    technique_roll_json: "[0.56,0.62]",
    schema_version: 1,
  },
  {
    id: "vibrato_control",
    label: "Vibrato control",
    score: 0.64,
    sessions_count: 3,
    last_session_date: "2026-10-25T17:45:00.000Z",
    easiness_factor: 2.3,
    interval_days: 2,
    next_review_date: "2026-10-28T17:45:00.000Z",
    sm2_repetitions: 1,
    technique_roll_json: "[0.6,0.66,0.64]",
    schema_version: 1,
  },
];

const JAM = {
  id: "ux-jam-1",
  date: "2026-10-24T20:20:00.000Z",
  duration_seconds: 150,
  scale_position_map: { pc_A: 4, pc_C: 3, pc_D: 2, pc_E: 2, pc_G: 1 },
  pitch_class_weight_map: { pc_A: 4, pc_C: 3, pc_D: 2, pc_E: 2, pc_G: 1 },
  position_weight_map: { 1: 3, 2: 2, 3: 1 },
  inferred_scale_label: "A minor pentatonic",
  inferred_mode: "minor_pentatonic",
  inference_confidence: "high",
  track_id: "am-blues-70",
  track_label: "A minor — slow blues shuffle",
  track_key: "A minor",
  track_bpm: 70,
  reliability_tags: ["steady_pulse", "clear_attack"],
  reliability_confidence: "high",
  reliability_signal_quality: 0.84,
  recurring_gestures: ["bend", "vibrato"],
  coach_summary: "You found a relaxed pocket and left useful space around the bends.",
  summary_bundle_json: null,
  phrases_json: null,
  summary_status: "ready",
};

const ANALYSIS_JOBS = [
  {
    jobId: "ux-analysis-job-1",
    sourceKind: "youtube",
    sourceRef: "https://www.youtube.com/watch?v=ux-audit",
    title: "Slow Blues Study",
    artist: null,
    submittedAt: "2026-10-27T15:48:00.000Z",
    updatedAt: NOW,
    status: "processing",
    progress: 0.42,
    stageLabel: "Separating stems…",
    error: null,
    errorCode: null,
  },
];

const PREFS = [
  { key: "onboarding_complete", value: "1" },
  { key: "mood_check_skip", value: "1" },
  { key: "session_skip_tune", value: "1" },
  { key: "output_tier", value: "intermediate" },
  { key: "home_practice_mode", value: "single" },
  { key: "experience_level", value: "intermediate" },
  {
    key: "taste_profile_json",
    value: JSON.stringify({
      style_label: "blues",
      technique_affinity: ["bending", "vibrato"],
      bpm_comfort_range: [70, 110],
      song_candidates: ["Midnight Blues"],
      source: "quiz",
    }),
  },
  { key: "analysis_jobs_json", value: JSON.stringify(ANALYSIS_JOBS) },
];

const PLAN = {
  plan_id: "ux-audit-plan",
  total_duration_seconds: 1500,
  slots: [
    {
      slot_id: "ux-plan-slot-1",
      slot_type: "song_section",
      duration_seconds: 1500,
      title: "Midnight Blues — Intro",
      coach_intro: "Settle into the pocket before adding the bend.",
      difficulty: 2,
      intent: "practice",
      target_skill: "timing",
    },
  ],
};

const DISCOVERY = {
  suggestions: [
    {
      job_id: "ux-recommendation-1",
      song_title: "Slow Blues Study",
      artist: "Harmoniq Studio",
      key: "A minor",
      style_label: "blues",
      tempo: 72,
      reasonLabel: "Matches your recent phrasing focus",
      similarityScore: 0.82,
      techniqueFocus: "bending",
    },
  ],
};

export async function waitForUxAuditDb(page: Page): Promise<void> {
  await page.waitForFunction(
    () =>
      new Promise<boolean>((resolve) => {
        const request = indexedDB.open("harmoniq_web_v1");
        request.onsuccess = () => {
          const db = request.result;
          const ready =
            db.objectStoreNames.contains("app_prefs") &&
            db.objectStoreNames.contains("lesson_cache") &&
            db.objectStoreNames.contains("lessons");
          db.close();
          resolve(ready);
        };
        request.onerror = () => resolve(false);
      }),
    undefined,
    { timeout: 15_000 },
  );
}

export async function seedUxAuditState(page: Page): Promise<void> {
  await page.evaluate(
    async (seed) => {
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open("harmoniq_web_v1");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
      });

      const required = [
        "app_prefs",
        "lesson_cache",
        "lessons",
        "sessions",
        "skill_nodes",
        "jam_snapshots",
      ];
      const missing = required.filter((name) => !db.objectStoreNames.contains(name));
      if (missing.length > 0) {
        db.close();
        throw new Error(`UX audit stores not initialized: ${missing.join(", ")}`);
      }

      try {
        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction(required, "readwrite");
          for (const pref of seed.prefs) tx.objectStore("app_prefs").put(pref);
          tx.objectStore("lesson_cache").put({
            id: "latest",
            lesson: seed.lesson,
            savedAt: seed.now,
          });
          tx.objectStore("lessons").put(seed.lessonRow);
          for (const row of seed.sessions) tx.objectStore("sessions").put(row);
          for (const row of seed.skillNodes) tx.objectStore("skill_nodes").put(row);
          for (const row of seed.jams) tx.objectStore("jam_snapshots").put(row);
          tx.oncomplete = () => resolve();
          tx.onerror = () => reject(tx.error ?? new Error("UX audit seed failed"));
          tx.onabort = () => reject(tx.error ?? new Error("UX audit seed aborted"));
        });
      } finally {
        db.close();
      }
    },
    {
      now: NOW,
      prefs: PREFS,
      lesson: LESSON,
      lessonRow: LESSON_ROW,
      sessions: SESSIONS,
      skillNodes: SKILL_NODES,
      jams: [JAM],
    },
  );
}

export async function installUxAuditApiMocks(page: Page): Promise<void> {
  await page.route("**/practice/plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLAN),
    });
  });
  await page.route("**/discovery/recommendations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(DISCOVERY),
    });
  });
  await page.route("**/curriculum/suggest", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ranked: [] }),
    });
  });
  await page.route("**/spotify/playback", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        is_playing: false,
        progress_ms: 0,
        playback_rate: 1,
        track_id: null,
        track_name: null,
        artists: [],
      }),
    });
  });
  await page.route("**/analyze/ux-analysis-job-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "processing",
        result: null,
        error: null,
        error_code: null,
        progress: 0.42,
        stage_label: "Separating stems…",
        processing_started_at: null,
        analysis_stage: "stems_separating",
        partial_result: null,
      }),
    });
  });
}

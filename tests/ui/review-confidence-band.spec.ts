import { expect, test, type Page } from '@playwright/test'

import { installUxAuditApiMocks, waitForUxAuditDb } from './support/uxSeed'

test.describe.configure({ timeout: 120_000 })

const JOB_ID = 'commit-184-review'

const BASE_LESSON: Record<string, unknown> = {
  job_id: JOB_ID,
  song_title: 'Confidence fixture',
  artist: 'Harmoniq',
  key: 'G major',
  tempo: 90,
  confidence_band: 'high',
  beat_grid: [0, 0.666, 1.333],
  bar_timestamps: [0, 2.666, 5.333],
  chord_timeline: {
    events: [
      { timestamp: 0, chord: 'G:maj', confidence: 0.92 },
      { timestamp: 2.666, chord: 'C:maj', confidence: 0.88 },
    ],
  },
  solo_notes: { notes: [] },
  sections: [
    {
      label: 'Main',
      start_time_seconds: 0,
      confidence: 0.9,
      chord_confidence: 0.9,
      instrument_confusion: 0.1,
    },
    {
      label: 'Bridge',
      start_time_seconds: 2.666,
      confidence: 0.4,
      chord_confidence: 0.4,
      instrument_confusion: 0.4,
    },
  ],
  instrument_confusion: null,
  instrument_confusion_per_section: [
    {
      section_index: 0,
      label: 'Main',
      start_time: 0,
      end_time: 2.666,
      instrument_confusion: 0.1,
      is_high_confusion: false,
      beat_count: 4,
      disagreement_count: 0,
    },
    {
      section_index: 1,
      label: 'Bridge',
      start_time: 2.666,
      end_time: 5.333,
      instrument_confusion: 0.4,
      is_high_confusion: true,
      beat_count: 4,
      disagreement_count: 2,
    },
  ],
}

function lessonWith(overrides: Record<string, unknown>): Record<string, unknown> {
  return { ...BASE_LESSON, ...overrides }
}

async function seedLesson(page: Page, lesson: Record<string, unknown>): Promise<void> {
  await page.evaluate(
    async ({ lesson, jobId }) => {
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open('harmoniq_web_v1')
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
      })
      try {
        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction(['lesson_cache', 'lessons'], 'readwrite')
          tx.objectStore('lesson_cache').put({
            id: 'latest',
            lesson,
            savedAt: new Date().toISOString(),
          })
          tx.objectStore('lessons').put({
            job_id: jobId,
            lesson_json: JSON.stringify(lesson),
            song_title: lesson.song_title,
            artist: lesson.artist,
            analyzed_at: new Date().toISOString(),
            section_count: Array.isArray(lesson.sections) ? lesson.sections.length : 0,
          })
          tx.oncomplete = () => resolve()
          tx.onerror = () => reject(tx.error ?? new Error('lesson seed failed'))
          tx.onabort = () => reject(tx.error ?? new Error('lesson seed aborted'))
        })
      } finally {
        db.close()
      }
    },
    { lesson, jobId: JOB_ID },
  )
}

async function openReview(page: Page, lesson: Record<string, unknown>): Promise<void> {
  await installUxAuditApiMocks(page)
  await page.route('**/analyze/*/corrections', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: JOB_ID,
        corrections: [],
        correction_count: 0,
        correction_coverage: 0,
      }),
    })
  })

  await page.goto('/')
  await waitForUxAuditDb(page)
  await seedLesson(page, lesson)
  await page.goto('/session/review')
  await page.reload()
}

test('review renders a plain-language confidence band without a percentage', async ({ page }) => {
  await openReview(page, lessonWith({}))

  const chip = page.getByTestId('confidence-band-chip')
  await expect(chip).toBeVisible({ timeout: 15_000 })
  await expect(chip).toContainText('Good match')
  await expect(chip).not.toContainText('%')
  await expect(page.getByLabel('Transcription confidence: Good match')).toBeVisible()
})

test('MT3-style lesson renders per-section confusion when song-level is null', async ({ page }) => {
  await openReview(page, lessonWith({ confidence_band: null }))

  const bars = page.getByTestId('per-section-confusion-bars')
  await expect(bars).toBeVisible({ timeout: 15_000 })
  await expect(bars).toContainText('Moderate')
  await expect(bars).not.toContainText('%')
  await expect(page.getByText(/Instrument confusion:/)).toHaveCount(0)
  await expect(page.getByTestId('confidence-band-chip')).toHaveCount(0)
})

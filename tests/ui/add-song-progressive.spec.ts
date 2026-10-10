import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

/**
 * Commit 152 — Progressive Analysis Reveal.
 *
 * Drives the add-song analyzing container through the full stage sequence and
 * asserts the three-step reveal: monolithic spinner → chord chart preview with
 * the refining banner → full score (TabViewport) on completion.
 *
 * Transport: SSE stream is aborted and the WebSocket is closed so the client
 * lands on HTTP polling (Commit 151 fallback chain), where each mocked GET
 * delivers the next scripted `JobStatus` frame.
 */

const JOB_ID = 'job-1'

const MUSICXML = fs.readFileSync(
  path.resolve(__dirname, '../../assets/musicxml-corpus/irregular-5-4.musicxml'),
  'utf8',
)

const PARTIAL = {
  chord_timeline: {
    events: [
      { timestamp: 0.0, chord: 'G:maj', confidence: 0.93 },
      { timestamp: 2.4, chord: 'D:maj', confidence: 0.88 },
    ],
  },
  bpm: 96.5,
  total_duration: 184.0,
}

const LESSON = {
  job_id: JOB_ID,
  song_title: 'Playtest',
  artist: 'The Testers',
  sections: [],
  musicxml: MUSICXML,
  tempo: 96.5,
  key: 'G major',
}

const baseFrame = {
  error: null,
  error_code: null,
  processing_started_at: 1_700_000_000,
}

const POLLS = [
  { ...baseFrame, status: 'processing', progress: 0.08, stage_label: 'Separating stems…', analysis_stage: 'stems_separating', partial_result: null, result: null },
  { ...baseFrame, status: 'processing', progress: 0.62, stage_label: 'Inferring chords…', analysis_stage: 'chords_inferring', partial_result: PARTIAL, result: null },
  { ...baseFrame, status: 'processing', progress: 0.78, stage_label: 'Transcribing solo…', analysis_stage: 'solo_inferring', partial_result: PARTIAL, result: null },
  { ...baseFrame, status: 'complete', progress: 1.0, stage_label: 'Done', analysis_stage: 'complete', partial_result: null, result: LESSON },
]

const CORS_HEADERS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,POST,OPTIONS',
  'access-control-allow-headers': 'content-type',
}

async function mockAnalyzeApi(page: Page): Promise<void> {
  // POST /analyze (JSON) — browser preflight included.
  await page.route('**/analyze', async (route) => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: CORS_HEADERS,
      body: JSON.stringify({ job_id: JOB_ID }),
    })
  })

  // SSE primary transport dies → chain advances to WebSocket.
  await page.route(`**/analyze/${JOB_ID}/stream`, (route) => route.abort('failed'))

  // WebSocket transport dies → chain lands on HTTP polling.
  await page.routeWebSocket('**/ws/analyze/*', (ws) => ws.close())

  // Polling: one scripted frame per GET, holding on the terminal frame.
  let pollIndex = 0
  await page.route(`**/analyze/${JOB_ID}`, async (route) => {
    const frame = POLLS[Math.min(pollIndex, POLLS.length - 1)]
    pollIndex += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: CORS_HEADERS,
      body: JSON.stringify(frame),
    })
  })
}

test('progressive reveal: spinner → chord preview + refining banner → full score', async ({ page }) => {
  // Cold Metro bundle + ~15s of scripted poll intervals.
  test.setTimeout(180_000)

  await mockAnalyzeApi(page)
  await page.goto('/add-song', { waitUntil: 'domcontentloaded' })

  // Web defaults to the Upload tab — switch to YouTube and submit.
  await expect(page.getByText('Add Song', { exact: true })).toBeVisible({ timeout: 30_000 })
  await page.getByRole('tab', { name: 'YouTube' }).click()
  await page.getByPlaceholder('https://www.youtube.com/watch?v=...').fill('https://www.youtube.com/watch?v=abc123')
  await page.getByLabel('Analyze YouTube URL').click()

  // Step 1 — monolithic spinner while the early stages report.
  await expect(page.getByText('Analyzing…')).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('[aria-label="chord chart preview"]')).toHaveCount(0)

  // Step 2 — chord preview + compact refining banner replace the spinner.
  const preview = page.locator('[aria-label="chord chart preview"]')
  await expect(preview).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('Analyzing…')).toHaveCount(0)

  // Partial payload drives the chips (G:maj / D:maj) and the duration/BPM meta.
  await expect(preview.getByText('G:maj')).toBeVisible({ timeout: 10_000 })
  await expect(preview.getByText('D:maj')).toBeVisible()

  // The compact banner carries the live stage text, elapsed clock and percent.
  const banner = page.locator('[aria-label="analysis refining banner"]')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('Transcribing solo…', { timeout: 20_000 })
  await expect(banner).toContainText('Elapsed')
  await expect(page.getByLabel('Progress 78 percent')).toBeVisible()

  // Step 3 — terminal frame swaps in the full score; spinner never returns.
  const score = page.locator('[aria-label="full score"]')
  await expect(score).toBeVisible({ timeout: 45_000 })
  await expect(preview).toHaveCount(0)
  await expect(page.getByText('Analyzing…')).toHaveCount(0)

  // AlphaTab renders the lesson MusicXML inside the slot.
  await expect(score.locator('svg.at-surface-svg').first()).toBeVisible({ timeout: 30_000 })

  // Done state confirms the lesson landed.
  await expect(page.getByText('Song ready')).toBeVisible({ timeout: 15_000 })
})

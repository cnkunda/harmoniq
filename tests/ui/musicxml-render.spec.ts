import { expect, test, type Page } from '@playwright/test'

const CORPUS = ['irregular-5-4', 'multi-voice-staff', 'nested-tuplets', 'syncopation'] as const

// AlphaTab DOM: `div.at-surface` contains one `svg.at-surface-svg` per
// rendered partial (multi-page scores split into several SVGs) — assert
// at least one non-empty score SVG exists.
const SURFACE = '.harmoniq-alphatab-scroll svg.at-surface-svg'

async function gotoCorpus(page: Page, name: string) {
  await page.goto(`/musicxml-render-test?file=${name}`, { waitUntil: 'domcontentloaded' })
  await expect(page.locator(`[aria-label="corpus-title:${name}"]`)).toBeVisible()
}

for (const name of CORPUS) {
  test(`MusicXML corpus renders without crash: ${name}`, async ({ page }) => {
    // First test pays for the cold Metro bundle; give it headroom.
    test.setTimeout(120_000)

    await gotoCorpus(page, name)

    const scoreSvg = page.locator(SURFACE).first()
    await expect(scoreSvg).toBeVisible({ timeout: 30_000 })
    await expect(scoreSvg).not.toBeEmpty()

    await expect(page.locator('[aria-label="corpus-error"]')).toHaveCount(0)

    await expect(page).toHaveScreenshot(`musicxml-corpus-${name}.png`, {
      animations: 'disabled',
      caret: 'hide',
    })
  })
}
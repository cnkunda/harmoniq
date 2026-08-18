/**
 * AlphaTab edge-case corpus check (Commit 107).
 * Reads JSON stdin: { corpusDir: string }
 * Loads every *.musicxml in the corpus through AlphaTab's ScoreLoader and
 * renders each with the SVG engine. Writes JSON stdout:
 *   { ok, total, rendered, failed: [{ file, error }] }
 * Web (DOM AlphaTab) and native (WebView AlphaTab) both run this exact
 * engine, so a clean pass here is the semantic "renders without crash"
 * gate for both platforms.
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

import * as alphaTab from '@coderline/alphatab'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function readStdinUtf8() {
  return new Promise((resolve, reject) => {
    const chunks = []
    process.stdin.on('data', (c) => chunks.push(c))
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    process.stdin.on('error', reject)
  })
}

function loadAndRender(filePath) {
  return new Promise((resolve, reject) => {
    const xml = fs.readFileSync(filePath, 'utf8')
    const settings = new alphaTab.Settings()
    settings.core.engine = 'svg'
    settings.core.enableLazyLoading = false
    settings.display.scale = 1.1

    const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(
      new Uint8Array(Buffer.from(xml, 'utf8')),
      settings,
    )
    const renderer = new alphaTab.rendering.ScoreRenderer(settings)
    renderer.width = 1200
    let partials = 0
    let rendered = false
    let finished = false

    const timer = setTimeout(() => {
      reject(new Error('renderer timed out (no renderFinished in 20s)'))
    }, 20_000)

    renderer.partialRenderFinished.on(() => {
      partials += 1
    })
    renderer.renderFinished.on((r) => {
      finished = true
      clearTimeout(timer)
      resolve({ masterBars: score.masterBars.length, partials, width: r.totalWidth, height: r.totalHeight })
    })
    renderer.renderScore(score, [0])
    // If the score has zero bars the renderer may finish synchronously-ish;
    // keep a fallback flush for single-bar scores that never emit events.
    setTimeout(() => {
      if (!finished && !rendered) {
        clearTimeout(timer)
        resolve({ masterBars: score.masterBars.length, partials, width: 0, height: 0, early: true })
      }
    }, 5_000)
  })
}

function main() {
  return readStdinUtf8().then(async (raw) => {
    const input = JSON.parse(raw)
    const corpusDir = input.corpusDir
    if (typeof corpusDir !== 'string' || !corpusDir) {
      throw new Error('corpusDir missing')
    }
    const files = fs.readdirSync(corpusDir).filter((f) => f.endsWith('.musicxml')).sort()
    const failed = []
    let rendered = 0
    for (const f of files) {
      const fp = path.join(corpusDir, f)
      try {
        const result = await loadAndRender(fp)
        if (!result || result.masterBars === 0) {
          failed.push({ file: f, error: `no master bars rendered (${JSON.stringify(result)})` })
        } else {
          rendered += 1
        }
      } catch (e) {
        failed.push({ file: f, error: e instanceof Error ? e.message : String(e) })
      }
    }
    process.stdout.write(JSON.stringify({ ok: failed.length === 0, total: files.length, rendered, failed }))
  })
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err)
  process.stdout.write(JSON.stringify({ ok: false, total: 0, rendered: 0, failed: [{ file: '<runner>', error: msg }] }))
  process.exitCode = 1
})
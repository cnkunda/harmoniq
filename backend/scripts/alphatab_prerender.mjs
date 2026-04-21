/**
 * AlphaTab Node-side SVG layout prerender (PRIORITIES §59).
 * Reads JSON stdin: { gp5_base64: string, preset?: { scale?: number, stretchForce?: number } }
 * Writes JSON stdout: { ok, master_bar_count, total_width, total_height, partial_count, partials }
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

function main() {
  return readStdinUtf8().then((raw) => {
    const input = JSON.parse(raw)
    const b64 = input.gp5_base64
    if (typeof b64 !== 'string' || !b64.trim()) {
      throw new Error('gp5_base64 missing')
    }
    const preset = input.preset && typeof input.preset === 'object' ? input.preset : {}
    const buf = Buffer.from(String(b64), 'base64')

    const pkgPath = path.join(__dirname, '..', 'node_modules', '@coderline', 'alphatab', 'package.json')
    let alphatabVersion = 'unknown'
    try {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'))
      if (pkg && typeof pkg.version === 'string') alphatabVersion = pkg.version
    } catch {
      /* ignore */
    }

    const settings = new alphaTab.Settings()
    settings.display.scale = typeof preset.scale === 'number' ? preset.scale : 1.1
    settings.display.stretchForce = typeof preset.stretchForce === 'number' ? preset.stretchForce : 1
    // Dark score ink — merge only colors; replacing `resources` drops fonts and yields empty partials.
    Object.assign(settings.display.resources, {
      mainGlyphColor: '#FFFFFF',
      secondaryGlyphColor: '#E8B86D',
      barSeparatorColor: '#6E5644',
      scoreInfoColor: '#8B7D6B',
      staffLineColor: '#6E5644',
      barNumberColor: '#8B7D6B',
    })
    settings.core.engine = 'svg'
    settings.core.enableLazyLoading = false

    const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(new Uint8Array(buf), settings)
    const renderer = new alphaTab.rendering.ScoreRenderer(settings)
    renderer.width = 1200

    const partials = []
    let finishedSize = { totalWidth: 0, totalHeight: 0 }

    renderer.preRender.on(() => {
      partials.length = 0
    })

    renderer.partialLayoutFinished.on((r) => {
      renderer.renderResult(r.id)
    })

    renderer.partialRenderFinished.on((r) => {
      partials.push({
        id: r.id,
        x: r.x,
        y: r.y,
        width: r.width,
        height: r.height,
        svg: typeof r.renderResult === 'string' ? r.renderResult : '',
      })
    })

    renderer.renderFinished.on((r) => {
      finishedSize = { totalWidth: r.totalWidth, totalHeight: r.totalHeight }
    })

    renderer.renderScore(score, [0])

    const out = {
      ok: true,
      alphatab_version: alphatabVersion,
      master_bar_count: score.masterBars.length,
      total_width: finishedSize.totalWidth,
      total_height: finishedSize.totalHeight,
      partial_count: partials.length,
      partials,
    }
    process.stdout.write(JSON.stringify(out))
  })
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err)
  process.stdout.write(JSON.stringify({ ok: false, error: msg }))
  process.exitCode = 1
})

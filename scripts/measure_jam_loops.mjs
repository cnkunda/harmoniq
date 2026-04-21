#!/usr/bin/env node
/**
 * One-shot: print duration (seconds) per bundled Jam MP3 via ffprobe.
 * Regenerate `durationMs` in `src/constants/backingTracks.ts` if loops change.
 *
 * Usage (repo root): node scripts/measure_jam_loops.mjs
 */
import { spawnSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { join } from 'node:path'

const dir = join(process.cwd(), 'assets', 'backing-tracks')
const files = readdirSync(dir).filter((f) => f.endsWith('.mp3')).sort()

for (const f of files) {
  const full = join(dir, f)
  const r = spawnSync(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', full],
    { encoding: 'utf8' },
  )
  if (r.error || r.status !== 0) {
    console.error(`ffprobe failed for ${f}:`, r.error?.message ?? r.stderr)
    process.exit(1)
  }
  const sec = parseFloat(r.stdout.trim())
  const ms = Math.round(sec * 1000)
  console.log(`${f}\t${sec}s\t${ms}ms`)
}

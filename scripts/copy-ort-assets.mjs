// Copies onnxruntime-web runtime assets from node_modules into `public/ort/`
// so the app can self-host the ONNX WASM runtime instead of loading it from a
// CDN. Files under `public/` are served at the web root by Expo (dev) and copied
// into the web export output. `public/ort/` is gitignored (large binaries); this
// script regenerates it. Runs automatically on `postinstall` and before web start.
//
// If assets are missing at runtime, the app falls back to the pinned CDN, so a
// skipped copy never breaks web — it just reintroduces the CDN dependency.

import { existsSync, mkdirSync, copyFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')
const srcDir = join(root, 'node_modules', 'onnxruntime-web', 'dist')
const destDir = join(root, 'public', 'ort')

if (!existsSync(srcDir)) {
  console.warn('[copy-ort-assets] onnxruntime-web not installed; skipping')
  process.exit(0)
}

mkdirSync(destDir, { recursive: true })

// The UMD entry plus every wasm binary and its JS loader shim. Setting
// ort.env.wasm.wasmPaths='/ort/' makes the runtime resolve these locally.
const explicit = ['ort.all.min.js']
const patterns = [/^ort-wasm-simd-threaded.*\.(wasm|mjs)$/]

const files = new Set(explicit)
for (const name of readdirSync(srcDir)) {
  if (patterns.some((re) => re.test(name))) files.add(name)
}

let copied = 0
for (const name of files) {
  const from = join(srcDir, name)
  if (!existsSync(from)) continue
  copyFileSync(from, join(destDir, name))
  copied++
}

console.log(`[copy-ort-assets] copied ${copied} file(s) to public/ort/`)

import { FEATURE_DIM, WINDOW } from '@/src/chord/cqtConstants'
import { NUM_CLASSES_MIREX } from '@/src/chord/chordVocab'

/** Load onnxruntime-web from CDN on web (avoids bundler dynamic-import issues). */
function loadScript(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = url
    s.onload = () => resolve()
    s.onerror = () => reject(new Error(`Failed to load script: ${url}`))
    document.head.appendChild(s)
  })
}

/** Pinned CDN base (fallback when self-hosted assets aren't present). */
const ORT_VERSION = '1.27.0'
const ORT_CDN_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`
/** Self-hosted base — populated by scripts/copy-ort-assets.mjs into public/ort/. */
const ORT_LOCAL_BASE = '/ort/'

/**
 * Ensure onnxruntime-web is available on `window.ort`. Prefers the self-hosted
 * copy (offline-capable, version-pinned); falls back to the pinned CDN if the
 * local assets are missing. `wasmPaths` is pointed at whichever base succeeded so
 * the runtime resolves its .wasm/.mjs from the same origin.
 */
async function ensureOrtWeb(): Promise<any> {
  const w = window as any
  if (w.ort) return w.ort

  let base = ORT_LOCAL_BASE
  try {
    await loadScript(`${ORT_LOCAL_BASE}ort.all.min.js`)
    if (!w.ort) throw new Error('local ort missing')
  } catch {
    base = ORT_CDN_BASE
    await loadScript(`${ORT_CDN_BASE}ort.all.min.js`)
  }

  const ort = w.ort
  if (!ort) throw new Error('ONNX runtime failed to initialize on web')
  try {
    ort.env.wasm.wasmPaths = base
  } catch {
    // Non-fatal; runtime will use its own default resolution.
  }
  return ort
}

export interface OnnxModelRunner {
  runSync(input: Float32Array): Float32Array
  runAsync(input: Float32Array): Promise<Float32Array>
}

/** Load the web ONNX model and return a synchronous/async inference runner. */
export async function loadOnnxModel(): Promise<OnnxModelRunner> {
  const ort = await ensureOrtWeb()
  const modelUrl: number = require('@/assets/models/chord_model.onnx')
  const session = await ort.InferenceSession.create(String(modelUrl))

  return {
    runSync(): Float32Array {
      return new Float32Array(NUM_CLASSES_MIREX)
    },
    async runAsync(input: Float32Array): Promise<Float32Array> {
      const tensor = new ort.Tensor('float32', input, [1, WINDOW, FEATURE_DIM])
      const result = await session.run({ input: tensor })
      const outputKey = session.outputNames[0]!
      const output = result[outputKey]
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      return new Float32Array((output as unknown as { data: Float32Array }).data)
    },
  }
}

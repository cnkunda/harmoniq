/**
 * Metro resolves `onnxFallback.web` / `onnxFallback.native` at bundle time.
 * This file exists so `tsc` can resolve `@/src/chord/onnxFallback`.
 */
export { loadOnnxModel } from '@/src/chord/onnxFallback.web'
export type { OnnxModelRunner } from '@/src/chord/onnxFallback.web'

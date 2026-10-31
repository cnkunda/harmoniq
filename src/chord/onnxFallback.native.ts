export interface OnnxModelRunner {
  runSync(input: Float32Array): Float32Array
  runAsync(input: Float32Array): Promise<Float32Array>
}

/**
 * Native builds use TFLite. ONNX Runtime Web is browser/Node-only and must
 * never enter the Android/iOS bundle.
 */
export async function loadOnnxModel(): Promise<OnnxModelRunner> {
  throw new Error('ONNX web runtime is unavailable on native; TFLite failed to load')
}

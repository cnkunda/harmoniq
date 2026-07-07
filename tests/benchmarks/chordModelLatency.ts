/**
 * On-device TFLite chord model latency benchmark (AC 6).
 *
 * Run this on a physical device (Pixel 7 / iPhone 13) to verify
 * that on-device inference completes in <120ms per frame.
 *
 * Usage (requires dev build with react-native-fast-tflite):
 *   npx expo run:android  (or :ios)
 *   # then in Metro: import and run this module
 *
 * The benchmark:
 *   1. Loads the TFLite model via react-native-fast-tflite
 *   2. Generates synthetic CQT input (all zeros, WINDOW × FEATURE_DIM)
 *   3. Warms up with 10 iterations
 *   4. Runs 100 timed iterations
 *   5. Reports p50, p95, p99, min, max, mean latency
 *   6. Asserts p95 < 120ms
 */

import type { TFLiteModel } from 'react-native-fast-tflite'

const WINDOW = 128
const FEATURE_DIM = 144
const WARMUP_ITERATIONS = 10
const BENCHMARK_ITERATIONS = 100
const LATENCY_THRESHOLD_MS = 120

function makeSyntheticInput(): Float32Array {
  return new Float32Array(WINDOW * FEATURE_DIM)
}

function percentile(sorted: number[], p: number): number {
  const idx = Math.ceil((p / 100) * sorted.length) - 1
  return sorted[Math.max(0, idx)]
}

export async function runChordModelLatencyBenchmark(): Promise<{
  passed: boolean
  p50: number
  p95: number
  p99: number
  min: number
  max: number
  mean: number
  iterations: number
}> {
  // 1. Load the model
  const { loadTensorflowModel } = await import('react-native-fast-tflite')
  const modelAsset: number = require('@/assets/models/chord_model.tflite')
  const model: TFLiteModel = await loadTensorflowModel(modelAsset, [])

  const input = makeSyntheticInput()
  const inputBuf = input.buffer.slice(input.byteOffset, input.byteOffset + input.byteLength) as ArrayBuffer

  // 2. Warmup
  for (let i = 0; i < WARMUP_ITERATIONS; i++) {
    model.run([inputBuf])
  }

  // 3. Benchmark
  const latencies: number[] = []
  for (let i = 0; i < BENCHMARK_ITERATIONS; i++) {
    const start = performance.now()
    model.run([inputBuf])
    const elapsed = performance.now() - start
    latencies.push(elapsed)
  }

  // 4. Stats
  const sorted = [...latencies].sort((a, b) => a - b)
  const p50 = percentile(sorted, 50)
  const p95 = percentile(sorted, 95)
  const p99 = percentile(sorted, 99)
  const min = sorted[0]!
  const max = sorted[sorted.length - 1]!
  const mean = latencies.reduce((a, b) => a + b, 0) / latencies.length
  const passed = p95 < LATENCY_THRESHOLD_MS

  // 5. Report
  console.log('--- Chord Model Latency Benchmark ---')
  console.log(`  Iterations: ${BENCHMARK_ITERATIONS}`)
  console.log(`  p50:  ${p50.toFixed(2)}ms`)
  console.log(`  p95:  ${p95.toFixed(2)}ms`)
  console.log(`  p99:  ${p99.toFixed(2)}ms`)
  console.log(`  min:  ${min.toFixed(2)}ms`)
  console.log(`  max:  ${max.toFixed(2)}ms`)
  console.log(`  mean: ${mean.toFixed(2)}ms`)
  console.log(`  Threshold: <${LATENCY_THRESHOLD_MS}ms (p95)`)
  console.log(`  Result: ${passed ? 'PASS' : 'FAIL'}`)

  return { passed, p50, p95, p99, min, max, mean, iterations: BENCHMARK_ITERATIONS }
}

/* eslint-disable @typescript-eslint/naming-convention */

/** Ambient module declarations for dynamically imported packages. */

declare module 'react-native-fast-tflite' {
  interface TFLiteModel {
    run(input: ArrayBuffer[]): ArrayBuffer[]
  }
  export function loadTensorflowModel(
    modelPath: number | string,
    delegates?: string[],
  ): Promise<TFLiteModel>
  export function useTensorflowModel(
    modelPath: number | string,
    delegates?: string[],
  ): TFLiteModel | null
}

declare module 'onnxruntime-web' {
  export class Tensor {
    constructor(type: string, data: Float32Array, dims: number[])
  }
  export class InferenceSession {
    static create(path: string): Promise<InferenceSession>
    run(feeds: Record<string, Tensor>): Promise<Record<string, Tensor>>
    readonly outputNames: string[]
  }
}

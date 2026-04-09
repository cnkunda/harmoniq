import type { RecordedTake, SessionRecorder } from '@/src/audio/recordSession.types'

class WebSessionRecorder implements SessionRecorder {
  private mediaRecorder: MediaRecorder | null = null
  private stream: MediaStream | null = null
  private chunks: BlobPart[] = []
  private startedAtMs = 0
  private active = false

  isRecording(): boolean {
    return this.active
  }

  async start(): Promise<void> {
    if (this.active) return
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Recording unavailable in this browser')
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm'
    const recorder = new MediaRecorder(stream, { mimeType })
    this.chunks = []
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data)
    }
    recorder.start()
    this.stream = stream
    this.mediaRecorder = recorder
    this.startedAtMs = Date.now()
    this.active = true
  }

  async stop(): Promise<RecordedTake> {
    const recorder = this.mediaRecorder
    if (!recorder || !this.active) {
      return { durationMs: 0, audioBytes: new Uint8Array(0), mimeType: 'audio/webm' }
    }
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve()
      recorder.stop()
    })
    const blob = new Blob(this.chunks, { type: recorder.mimeType || 'audio/webm' })
    const bytes = new Uint8Array(await blob.arrayBuffer())
    this.stream?.getTracks().forEach((t) => t.stop())
    this.stream = null
    this.mediaRecorder = null
    this.chunks = []
    const durationMs = Math.max(0, Date.now() - this.startedAtMs)
    this.startedAtMs = 0
    this.active = false
    return {
      durationMs,
      audioBytes: bytes,
      mimeType: blob.type || 'audio/webm',
    }
  }
}

export function createSessionRecorder(): SessionRecorder {
  return new WebSessionRecorder()
}

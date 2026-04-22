import { Audio } from 'expo-av'

import type { RecordedTake, SessionRecorder } from '@/src/audio/recordSession.types'
import { globalAudioManager } from './GlobalAudioManager'

class NativeSessionRecorder implements SessionRecorder {
  private recording: Audio.Recording | null = null
  private startedAtMs = 0
  private active = false
  private recorderInstanceId = `session-recorder-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

  isRecording(): boolean {
    return this.active
  }

  async start(): Promise<void> {
    if (this.active) return
    const perm = await Audio.requestPermissionsAsync()
    if (!perm.granted) throw new Error('MIC_PERMISSION_DENIED')
    await globalAudioManager.setRecordingMode()
    const rec = new Audio.Recording()
    await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY)
    await rec.startAsync()
    this.recording = rec
    this.startedAtMs = Date.now()
    this.active = true

    // Register recorder with GlobalAudioManager
    globalAudioManager.registerInstance(
      this.recorderInstanceId,
      'expo-recording',
      this.recording,
      async () => {
        if (this.recording && this.active) {
          await this.stop()
        }
      },
    )
  }

  async stop(): Promise<RecordedTake> {
    const rec = this.recording
    if (!rec || !this.active) {
      return { durationMs: 0, audioBytes: new Uint8Array(0), mimeType: 'audio/m4a' }
    }
    await rec.stopAndUnloadAsync()
    const uri = rec.getURI()
    this.recording = null
    const durationMs = Math.max(0, Date.now() - this.startedAtMs)
    this.startedAtMs = 0
    this.active = false
    await globalAudioManager.resetToPlaybackMode()

    // Unregister from GlobalAudioManager
    void globalAudioManager.unregisterInstance(this.recorderInstanceId)

    if (!uri) {
      return { durationMs, audioBytes: new Uint8Array(0), mimeType: 'audio/m4a' }
    }
    const res = await fetch(uri)
    const bytes = new Uint8Array(await res.arrayBuffer())
    return {
      durationMs,
      audioBytes: bytes,
      mimeType: 'audio/m4a',
    }
  }
}

export function createSessionRecorder(): SessionRecorder {
  return new NativeSessionRecorder()
}

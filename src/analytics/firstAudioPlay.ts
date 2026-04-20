/** Fires once per JS runtime — first audible practice output (Jam, Listen, or onboarding reference). */

let fired = false

export type FirstAudioPlaySource =
  | 'demo_listen'
  | 'lesson_listen'
  | 'jam_classic'
  | 'jam_ai'
  | 'onboarding_reference'

export function logFirstAudioPlay(payload: { source: FirstAudioPlaySource; job_id?: string | null }): void {
  if (fired) return
  fired = true
  const line = `[first_audio_play] ${payload.source}${payload.job_id ? ` job_id=${payload.job_id}` : ''}`
  if (__DEV__) {
    console.info(line)
  }
  try {
    ;(globalThis as { __HARMONIQ_FIRST_AUDIO__?: string }).__HARMONIQ_FIRST_AUDIO__ = line
  } catch {
    /* ignore */
  }
}

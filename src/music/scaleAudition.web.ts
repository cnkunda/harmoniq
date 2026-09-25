export interface ScaleAuditionPlayer {
  playNote(midiNote: number): Promise<void>
  playScale(rootMidi: number, intervals: number[], bpm: number, onNote?: (midi: number) => void): Promise<void>
  stopPlayback(): void
}

let audioCtx: AudioContext | null = null
let stopFlag = false

function getContext(): AudioContext {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new AudioContext()
  }
  if (audioCtx.state === 'suspended') {
    void audioCtx.resume()
  }
  return audioCtx
}

function midiToFrequency(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

function playTone(
  ctx: AudioContext,
  frequency: number,
  startTime: number,
  duration: number,
  volume: number,
): void {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(frequency, startTime)
  gain.gain.setValueAtTime(0, startTime)
  gain.gain.linearRampToValueAtTime(volume, startTime + 0.008)
  gain.gain.setValueAtTime(volume, startTime + duration - 0.05)
  gain.gain.linearRampToValueAtTime(0, startTime + duration)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(startTime)
  osc.stop(startTime + duration + 0.01)
}

export async function playNote(midiNote: number): Promise<void> {
  const ctx = getContext()
  const freq = midiToFrequency(midiNote)
  playTone(ctx, freq, ctx.currentTime + 0.02, 0.5, 0.18)
}

export async function playScale(
  rootMidi: number,
  intervals: number[],
  bpm: number,
  onNote?: (midi: number) => void,
): Promise<void> {
  stopFlag = false
  const ctx = getContext()
  const beatDuration = 60 / bpm
  const noteDuration = beatDuration * 0.85

  for (let i = 0; i < intervals.length; i++) {
    if (stopFlag) break
    const midi = rootMidi + intervals[i]
    const freq = midiToFrequency(midi)
    const startTime = ctx.currentTime + 0.05
    playTone(ctx, freq, startTime, noteDuration, 0.18)
    onNote?.(midi)
    await new Promise((resolve) => setTimeout(resolve, beatDuration * 1000))
  }
}

export function stopPlayback(): void {
  stopFlag = true
}

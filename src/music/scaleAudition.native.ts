import { Audio } from 'expo-av'
import { File, Paths, Directory } from 'expo-file-system'

const SAMPLE_RATE = 44100
const NOTE_DURATION_SEC = 0.5

let activeSound: Audio.Sound | null = null
let stopFlag = false

function midiToFrequency(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

function generateWavBytes(frequency: number, durationSec: number): Uint8Array {
  const numSamples = Math.floor(SAMPLE_RATE * durationSec)
  const buffer = new ArrayBuffer(44 + numSamples * 2)
  const view = new DataView(buffer)

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + numSamples * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, SAMPLE_RATE, true)
  view.setUint32(28, SAMPLE_RATE * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, numSamples * 2, true)

  const volume = 0.3
  for (let i = 0; i < numSamples; i++) {
    const t = i / SAMPLE_RATE
    const envelope = Math.min(1, t / 0.01, (durationSec - t) / 0.05, 1)
    const sample = Math.sin(2 * Math.PI * frequency * t) * volume * envelope
    const clamped = Math.max(-1, Math.min(1, sample))
    view.setInt16(44 + i * 2, clamped * 32767, true)
  }

  return new Uint8Array(buffer)
}

function cacheDir(): Directory {
  return new Directory(Paths.cache, 'scale_audition')
}

function noteFileName(midi: number): string {
  return `note_${midi}.wav`
}

async function ensureCacheDir(): Promise<Directory> {
  const dir = cacheDir()
  if (!dir.exists) {
    dir.create({ intermediates: true, idempotent: true })
  }
  return dir
}

async function writeNoteWav(midiNote: number): Promise<File> {
  const dir = await ensureCacheDir()
  const file = dir.createFile(noteFileName(midiNote), 'audio/wav')
  const freq = midiToFrequency(midiNote)
  const bytes = generateWavBytes(freq, NOTE_DURATION_SEC)
  file.write(bytes)
  return file
}

async function playWavFile(file: File): Promise<void> {
  await Audio.setAudioModeAsync({
    playsInSilentModeIOS: true,
    staysActiveInBackground: false,
    allowsRecordingIOS: false,
  })

  const { sound } = await Audio.Sound.createAsync(
    { uri: file.uri },
    { shouldPlay: true, volume: 0.5 },
  )
  activeSound = sound
  return new Promise<void>((resolve) => {
    sound.setOnPlaybackStatusUpdate((status) => {
      if (!status || stopFlag) {
        if (stopFlag) {
          void sound.unloadAsync().catch(() => {})
          activeSound = null
        }
        resolve()
        return
      }
      if ('didJustFinish' in status && status.didJustFinish) {
        void sound.unloadAsync().catch(() => {})
        activeSound = null
        resolve()
      }
    })
  })
}

export async function playNote(midiNote: number): Promise<void> {
  if (activeSound) {
    await activeSound.stopAsync().catch(() => {})
    await activeSound.unloadAsync().catch(() => {})
    activeSound = null
  }

  const file = await writeNoteWav(midiNote)
  await playWavFile(file)
}

export async function playScale(
  rootMidi: number,
  intervals: number[],
  bpm: number,
  onNote?: (midi: number) => void,
): Promise<void> {
  stopFlag = false
  const beatMs = (60 / bpm) * 1000
  const dir = await ensureCacheDir()

  const files: File[] = []
  for (let i = 0; i < intervals.length; i++) {
    if (stopFlag) break
    const midi = rootMidi + intervals[i]
    const file = dir.createFile(`scale_${i}_${midi}.wav`, 'audio/wav')
    const freq = midiToFrequency(midi)
    const bytes = generateWavBytes(freq, NOTE_DURATION_SEC)
    file.write(bytes)
    files.push(file)
  }

  for (let i = 0; i < files.length; i++) {
    if (stopFlag) break
    await playWavFile(files[i])
    const midi = rootMidi + intervals[i]
    onNote?.(midi)
    if (i < files.length - 1 && !stopFlag) {
      await new Promise((resolve) => setTimeout(resolve, Math.max(0, beatMs - NOTE_DURATION_SEC * 1000)))
    }
  }

  try {
    const cache = cacheDir()
    if (cache.exists) cache.delete()
  } catch {}
}

export function stopPlayback(): void {
  stopFlag = true
  if (activeSound) {
    void activeSound.stopAsync().catch(() => {})
    void activeSound.unloadAsync().catch(() => {})
    activeSound = null
  }
}

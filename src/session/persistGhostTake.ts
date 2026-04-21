import type { RecordedTake } from '@/src/audio/recordSession.types'
import type { LessonJSON } from '@/src/types'

import type { GhostReferenceRow } from '@/src/db/types'

function bytesToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(bytes).toString('base64')
  }
  let bin = ''
  const chunk = 8192
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, Math.min(bytes.length, i + chunk)))
  }
  return btoa(bin)
}

function extensionForMime(mime: string): string {
  const m = mime.toLowerCase()
  if (m.includes('webm')) return 'webm'
  if (m.includes('wav')) return 'wav'
  if (m.includes('m4a') || m.includes('mp4')) return 'm4a'
  return 'bin'
}

export type PersistGhostTakeInput = {
  take: RecordedTake
  lesson: LessonJSON | null | undefined
  sectionIndex: number
  anchorSec: number
}

/**
 * Writes on-disk audio on native; stores inline base64 on web for DB-backed ghost playback.
 */
export async function prepareGhostTakePayload(input: PersistGhostTakeInput): Promise<{
  waveform_user_path: string | null
  ghost_audio_base64: string | null
  ghost_recording_mime: string | null
}> {
  const { take, lesson, sectionIndex, anchorSec } = input
  const jobId = typeof lesson?.job_id === 'string' ? lesson.job_id.trim() : ''
  if (!jobId || take.audioBytes.length === 0) {
    return { waveform_user_path: null, ghost_audio_base64: null, ghost_recording_mime: null }
  }

  const ext = extensionForMime(take.mimeType)
  const baseName = `ghost_${jobId}_${sectionIndex}_${Date.now().toString(36)}.${ext}`

  if (typeof window !== 'undefined') {
    void anchorSec
    return {
      waveform_user_path: null,
      ghost_audio_base64: bytesToBase64(take.audioBytes),
      ghost_recording_mime: take.mimeType || null,
    }
  }

  const FileSystem = await import('expo-file-system/legacy')
  const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
  if (!dir) {
    console.warn('[persistGhostTake] no writable directory — ghost inline base64 fallback skipped on native')
    return {
      waveform_user_path: null,
      ghost_audio_base64: bytesToBase64(take.audioBytes),
      ghost_recording_mime: take.mimeType || null,
    }
  }
  const path = `${dir}${baseName}`
  await FileSystem.writeAsStringAsync(path, bytesToBase64(take.audioBytes), {
    encoding: FileSystem.EncodingType.Base64,
  })
  return { waveform_user_path: path, ghost_audio_base64: null, ghost_recording_mime: take.mimeType || null }
}

/** Resolve a playable URI for the ghost clip (web blob URL or file URI). Caller may revoke blob URLs when done. */
export function ghostReferenceToPlaybackUri(row: GhostReferenceRow): string | null {
  if (typeof row.ghost_audio_base64 === 'string' && row.ghost_audio_base64.length > 0) {
    try {
      const bin = atob(row.ghost_audio_base64)
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      const mime =
        typeof row.ghost_recording_mime === 'string' && row.ghost_recording_mime.trim()
          ? row.ghost_recording_mime.trim()
          : 'audio/webm'
      const blob = new Blob([bytes], { type: mime })
      return URL.createObjectURL(blob)
    } catch (e) {
      console.warn('[ghost] inline base64 decode failed', e)
      return null
    }
  }
  const p = row.waveform_user_path
  if (typeof p === 'string' && p.length > 0) {
    return p
  }
  return null
}

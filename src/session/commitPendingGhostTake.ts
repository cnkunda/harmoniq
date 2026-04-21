import { getAppPref, insertSessionRow } from '@/src/db/client'
import { PREF_MOOD_CHECK_LAST_MOOD } from '@/src/db/schema'
import type { LessonJSON } from '@/src/types'

import { prepareGhostTakePayload } from '@/src/session/persistGhostTake'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'

/** Persists flagged ghost take once (Review entry or scoring path). Idempotent via pending flag. */
export async function commitPendingGhostTakeIfNeeded(params: {
  lesson: LessonJSON | null | undefined
  sectionIndex: number
}): Promise<boolean> {
  const store = useSessionPlayStore.getState()
  const { pendingGhostReference, latestTake, lastTakeAnchorSec } = store
  if (!pendingGhostReference || !latestTake?.audioBytes?.length) {
    return false
  }

  const anchor =
    typeof lastTakeAnchorSec === 'number' && Number.isFinite(lastTakeAnchorSec) ? lastTakeAnchorSec : 0

  const { lesson, sectionIndex } = params
  const jobId = typeof lesson?.job_id === 'string' ? lesson.job_id.trim() : ''
  const section =
    lesson?.sections?.[sectionIndex] && typeof lesson.sections[sectionIndex] === 'object'
      ? lesson.sections[sectionIndex]
      : null

  const payload = await prepareGhostTakePayload({
    take: latestTake,
    lesson,
    sectionIndex,
    anchorSec: anchor,
  })

  if (!jobId) {
    console.warn('[ghost] persist skipped — missing job_id')
    store.setPendingGhostReference(false)
    return false
  }

  const sectionLabel =
    section != null && typeof (section as Record<string, unknown>).label === 'string'
      ? ((section as Record<string, unknown>).label as string)
      : null

  await insertSessionRow({
    id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    song_title: typeof lesson?.song_title === 'string' ? lesson.song_title : null,
    artist: typeof lesson?.artist === 'string' ? lesson.artist : null,
    section_label: sectionLabel,
    date: new Date().toISOString(),
    coach_review: 'Ghost reference take',
    pitch_accuracy: null,
    phrasing_score: null,
    nodes_targeted: [],
    review_snapshot: null,
    waveform_user_path: payload.waveform_user_path,
    waveform_ref_path: null,
    job_id: jobId,
    section_index: sectionIndex,
    is_ghost_reference: true,
    ghost_anchor_sec: anchor,
    ghost_audio_base64: payload.ghost_audio_base64,
    ghost_recording_mime: payload.ghost_recording_mime,
    mood: ((await getAppPref(PREF_MOOD_CHECK_LAST_MOOD)) as 'focused' | 'loose' | 'tired' | 'on_fire' | null) ?? null,
  })

  store.setPendingGhostReference(false)
  console.info('[ghost] persisted ghost reference for section', jobId, sectionIndex)
  return true
}

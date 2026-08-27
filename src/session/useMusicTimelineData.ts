import { useLessonStore } from '@/src/stores/lessonStore'
import type { ChordEvent, SoloNoteEvent } from '@/src/context/MusicContext'

/**
 * Shared hook to extract chordEvents, soloNotes, and barTimestamps for MusicProvider.
 * Prefers section-level data, falls back to lesson-level (same pattern as study.tsx:133-136).
 */
export function useMusicTimelineData(): {
  chordEvents: ChordEvent[] | null
  soloNotesArr: SoloNoteEvent[] | null
  barTimestamps: number[] | null
} {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = (lesson?.sections?.[lessonSectionIndex] ?? null) as Record<string, unknown> | null

  const chordEvents =
    (section as { chord_timeline?: { events: ChordEvent[] } } | null)?.chord_timeline?.events ??
    (lesson as { chord_timeline?: { events: ChordEvent[] } } | null)?.chord_timeline?.events ??
    null

  const soloNotesArr =
    (section as { solo_notes?: { notes: SoloNoteEvent[] } } | null)?.solo_notes?.notes ??
    (lesson as { solo_notes?: { notes: SoloNoteEvent[] } } | null)?.solo_notes?.notes ??
    null

  const barTimestamps = (lesson as { bar_timestamps?: number[] } | null)?.bar_timestamps ?? null

  return { chordEvents, soloNotesArr, barTimestamps }
}

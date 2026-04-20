import { Text, View } from 'react-native'

import { SESSION_PLAYBACK_CARD_CLASS } from '@/src/constants/sessionPlaybackCard'
import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'
import type { TabNoteQueueEntry } from '@/src/session/usePlayCapture'

import { PlayPitchBeatCard } from './PlayPitchBeatCard'
import { PlayPitchLadderVertical } from './PlayPitchLadderVertical'

export type PlayStemRowScoringCardProps = {
  currentStreak: number
  adaptedCentsTolerance: number
  innerToleranceCents: number
  queue: TabNoteQueueEntry[]
  beats: NoteResultLabel[]
  noteLabels: string[]
  recording: boolean
  centsFromTarget: number | null | undefined
  targetMidi: number
  nextPreviewMidi?: number | null
  windowResult?: NoteResultLabel | null
  windowFlashToken?: number
}

/**
 * Third-column replacement for ListenStemPanel on Play: targets + beat strip + live ladder,
 * using the same shell as “Current lesson” / “Metronome”.
 */
export function PlayStemRowScoringCard({
  currentStreak,
  adaptedCentsTolerance,
  innerToleranceCents,
  queue,
  beats,
  noteLabels,
  recording,
  centsFromTarget,
  targetMidi,
  nextPreviewMidi,
  windowResult,
  windowFlashToken,
}: PlayStemRowScoringCardProps) {
  return (
    <View className={`${SESSION_PLAYBACK_CARD_CLASS} min-h-0`}>
      <Text className="mb-2 shrink-0 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
        Pitch & score
      </Text>
      <View className="min-h-0 flex-1 flex-col gap-3 lg:flex-row lg:items-stretch">
        <PlayPitchBeatCard
          embedded
          currentStreak={currentStreak}
          adaptedCentsTolerance={adaptedCentsTolerance}
          innerToleranceCents={innerToleranceCents}
          queue={queue}
          beats={beats}
          noteLabels={noteLabels}
        />
        <PlayPitchLadderVertical
          embedded
          cents={centsFromTarget}
          isActive={recording}
          adaptedCentsTolerance={adaptedCentsTolerance}
          targetMidi={targetMidi}
          nextTargetMidi={nextPreviewMidi}
          windowResult={windowResult}
          windowFlashToken={windowFlashToken}
        />
      </View>
    </View>
  )
}

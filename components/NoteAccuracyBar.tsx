import { View } from 'react-native'

import type { AccuracyLabel } from '@/src/session/noteAccuracyBeats'

const BLOCK: Record<AccuracyLabel, string> = {
  hit: 'bg-success',
  close: 'bg-amber-accent',
  miss: 'bg-danger',
}

export interface NoteAccuracyBarProps {
  beats: AccuracyLabel[]
  maxVisible?: number
}

/** Compact beat-by-beat accuracy timeline (PRIORITIES §49). */
export function NoteAccuracyBar({ beats, maxVisible = 24 }: NoteAccuracyBarProps) {
  const slice = beats.length > maxVisible ? beats.slice(-maxVisible) : beats
  if (slice.length === 0) return null
  return (
    <View className="flex-row gap-0.5">
      {slice.map((b, i) => (
        <View
          key={`${i}-${b}`}
          className={`min-w-[6px] flex-1 rounded-sm ${BLOCK[b]}`}
          style={{ height: 12 }}
        />
      ))}
    </View>
  )
}

import { Text, View } from 'react-native'

import type { ChordDetection } from '@/src/chord/chordModelTypes'
import { isNoChord } from '@/src/chord/chordVocab'
import { formatChordDisplay } from '@/src/music/chordVoicing'

export interface ChordHistoryStreamProps {
  /** Recent chord detections (newest first). */
  history: readonly ChordDetection[]
}

/**
 * Horizontal stream of the last 8 chord detections.
 * Each chord shown as a small badge with opacity fading with age.
 */
export function ChordHistoryStream({ history }: ChordHistoryStreamProps) {
  if (history.length === 0) return null

  return (
    <View className="mt-3 flex-row items-center gap-1.5">
      <Text className="mr-1 font-sans text-[10px] text-muted-brown">Recent:</Text>
      {history.slice(0, 8).map((detection, i) => {
        const opacity = Math.max(0.3, 1 - i * 0.1)
        const label = isNoChord(detection.chord) ? '—' : formatChordDisplay(detection.chord)
        return (
          <View
            key={`${detection.timestamp}-${i}`}
            className="rounded-md border border-wood-600/40 bg-wood-900/60 px-2 py-0.5"
            style={{ opacity }}
          >
            <Text className="font-mono text-[11px] text-cream">{label}</Text>
          </View>
        )
      })}
    </View>
  )
}



import { View, Text } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { SECTION_EYEBROW_CLASS } from '@/src/constants/uiTokens'
import { formatChordDisplay } from '@/src/music/chordVoicing'
import { useCorrectionStore } from '@/src/stores/correctionStore'
import type { ChordCorrection, NoteCorrection, VoicingOverride } from '@/src/types'

type CorrectionHistoryProps = {
  jobId: string
  onRevert: (correctionId: string) => void
}

/**
 * Displays correction history with ability to revert individual corrections.
 */
export function CorrectionHistory({ jobId, onRevert }: CorrectionHistoryProps) {
  const corrections = useCorrectionStore((s) => s.corrections[jobId])
  if (!corrections) return null

  const allItems: Array<{ id: string; type: string; label: string; detail: string; timestamp: number }> = []

  for (const c of corrections.chordCorrections) {
    allItems.push({
      id: c.id,
      type: 'chord',
      label: `${formatChordDisplay(c.originalChord)} → ${formatChordDisplay(c.correctedChord)}`,
      detail: `Chord correction at event ${c.eventIndex}`,
      timestamp: c.timestamp,
    })
  }
  for (const c of corrections.noteCorrections) {
    allItems.push({
      id: c.id,
      type: 'note',
      label: `Note #${c.noteIndex}: pitch ${c.originalPitch} → ${c.correctedPitch ?? c.originalPitch}`,
      detail: `Note correction`,
      timestamp: c.timestamp,
    })
  }
  for (const v of corrections.voicingOverrides) {
    allItems.push({
      id: v.id,
      type: 'voicing',
      label: `Voicing: ${v.correctedShape}`,
      detail: `Voicing override`,
      timestamp: v.timestamp,
    })
  }

  // Sort by timestamp descending
  allItems.sort((a, b) => b.timestamp - a.timestamp)

  if (allItems.length === 0) return null

  return (
    <View>
      <Text className={SECTION_EYEBROW_CLASS}>Corrections ({allItems.length})</Text>
      <View className="mt-2 gap-1.5">
        {allItems.map((item) => (
          <View
            key={item.id}
            className="flex-row items-center justify-between rounded-lg border border-wood-600/30 bg-wood-900/20 px-3 py-2"
          >
            <View className="flex-1">
              <Text className="font-sans text-xs text-cream">{item.label}</Text>
              <Text className="text-[10px] text-muted-brown">{item.detail}</Text>
            </View>
            <AnimatedPressable
              onPress={() => onRevert(item.id)}
              className="rounded-full border border-wood-600/40 bg-wood-900/10 px-2 py-1"
            >
              <Text className="font-sans text-[10px] text-amber-accent">Revert</Text>
            </AnimatedPressable>
          </View>
        ))}
      </View>
    </View>
  )
}

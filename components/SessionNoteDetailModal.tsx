import { Modal, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { NoteDetailCard } from '@/components/NoteDetailCard'
import type { NoteSelectionDetail } from '@/src/music/noteSelectionDetail'

type SessionNoteDetailModalProps = {
  detail: NoteSelectionDetail | null
  visible: boolean
  onClose: () => void
  /** Commit B9: Current chord's voicing label to display as a badge. */
  currentChordVoicing?: string | null
}

export function SessionNoteDetailModal({ detail, visible, onClose, currentChordVoicing }: SessionNoteDetailModalProps) {
  return (
    <Modal visible={visible && detail != null} transparent animationType="fade" onRequestClose={onClose}>
      <View className="flex-1">
        <AnimatedPressable
          className="absolute inset-0 bg-wood-900/50"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close note details"
        />
        <View className="absolute inset-0 bg-wood-900/35" pointerEvents="none" />

        <View className="flex-1 justify-center px-8 pb-12 pt-12">
          <AnimatedPressable className="absolute inset-0" onPress={onClose} />
          {detail ? (
            <View className="w-full max-w-lg self-center rounded-3xl border border-wood-600/70 bg-wood-900 p-4">
              {currentChordVoicing ? (
                <View className="mb-3 flex-row items-center gap-3">
                  <View className="rounded-full border border-wood-600/50 px-2.5 py-1">
                    <Text className="font-mono text-[10px] text-amber-accent/70">
                      {currentChordVoicing}
                    </Text>
                  </View>
                </View>
              ) : null}
              <NoteDetailCard
                noteName={detail.noteName}
                scaleDegree={detail.degree}
                fingerLine={detail.fingerLine}
                alternateFingerLines={detail.alternateFingerLines}
                coachText={detail.coach}
                onDismiss={onClose}
                chordToneStatus={detail.chordToneStatus}
                harmonicDegree={detail.harmonicDegree}
                confidence={detail.confidence}
              />
            </View>
          ) : null}
        </View>
      </View>
    </Modal>
  )
}

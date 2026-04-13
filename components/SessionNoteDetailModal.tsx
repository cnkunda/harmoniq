import { Modal, Pressable, View } from 'react-native'

import { NoteDetailCard } from '@/components/NoteDetailCard'
import type { NoteSelectionDetail } from '@/src/music/noteSelectionDetail'

type SessionNoteDetailModalProps = {
  detail: NoteSelectionDetail | null
  visible: boolean
  onClose: () => void
}

export function SessionNoteDetailModal({ detail, visible, onClose }: SessionNoteDetailModalProps) {
  return (
    <Modal visible={visible && detail != null} transparent animationType="fade" onRequestClose={onClose}>
      <View className="flex-1">
        <Pressable
          className="absolute inset-0 bg-black/50"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close note details"
        />
        <View className="absolute inset-0 bg-wood-900/35" pointerEvents="none" />

        <View className="flex-1 justify-center px-8 pb-12 pt-12">
          <Pressable className="absolute inset-0" onPress={onClose} />
          {detail ? (
            <View className="w-full max-w-lg self-center rounded-3xl border border-wood-600/70 bg-wood-900 p-4">
              <NoteDetailCard
                noteName={detail.noteName}
                scaleDegree={detail.degree}
                fingerLine={detail.fingerLine}
                alternateFingerLines={detail.alternateFingerLines}
                coachText={detail.coach}
                onDismiss={onClose}
              />
            </View>
          ) : null}
        </View>
      </View>
    </Modal>
  )
}

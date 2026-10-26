import { Modal, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Button } from '@/components/Button'

export interface ConfirmDialogProps {
  visible: boolean
  title: string
  message: string
  confirmLabel: string
  cancelLabel?: string
  destructive?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Cross-platform confirmation dialog (native + web). */
export function ConfirmDialog({
  visible,
  title,
  message,
  confirmLabel,
  cancelLabel = 'Cancel',
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={busy ? undefined : onCancel}>
      <View className="flex-1">
        <AnimatedPressable
          className="absolute inset-0 bg-wood-900/70"
          onPress={busy ? undefined : onCancel}
          disabled={busy}
          haptic="none"
          accessibilityRole="button"
          accessibilityLabel="Dismiss dialog"
        />
        <View className="flex-1 justify-center px-5 py-10">
          <View
            className="w-full max-w-md self-center overflow-hidden rounded-2xl border border-wood-600/70 bg-wood-900 p-5"
            accessibilityRole="alert"
            accessibilityLabel={title}
          >
            <Text className="font-serif text-2xl text-cream">{title}</Text>
            <Text className="mt-2 font-sans text-sm leading-relaxed text-muted-brown">{message}</Text>
            <View className="mt-6 flex-row gap-3">
              <Button
                label={cancelLabel}
                variant="secondary"
                onPress={onCancel}
                disabled={busy}
                containerClassName="flex-1"
              />
              <Button
                label={confirmLabel}
                variant={destructive ? 'danger' : 'primary'}
                onPress={onConfirm}
                loading={busy}
                containerClassName="flex-1"
              />
            </View>
          </View>
        </View>
      </View>
    </Modal>
  )
}

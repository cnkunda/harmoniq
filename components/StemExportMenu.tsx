import { FileArchive, FileAudio } from 'lucide-react-native'
import { ActivityIndicator, Modal, Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'
import { STEM_LABELS, type StemKey } from '@/src/constants/stems'

export type StemExportMenuProps = {
  visible: boolean
  stems: StemKey[]
  busyKey: string | null
  onClose: () => void
  onExportAll: () => void
  onExportStem: (stem: StemKey) => void
}

export function StemExportMenu({
  visible,
  stems,
  busyKey,
  onClose,
  onExportAll,
  onExportStem,
}: StemExportMenuProps) {
  const busy = busyKey !== null

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={busy ? undefined : onClose}>
      <View className="flex-1">
        <AnimatedPressable
          className="absolute inset-0 bg-wood-900/60"
          onPress={onClose}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="Close stem export"
        />
        <View className="flex-1 justify-end px-4 pb-8 pt-12">
          <View className="rounded-3xl border border-wood-600/70 bg-wood-900 p-4" accessibilityViewIsModal>
            <View className="mb-3 flex-row items-center justify-between">
              <Text className="font-serif text-lg text-cream">Export stems</Text>
              <AnimatedPressable
                onPress={onClose}
                disabled={busy}
                haptic="light"
                className="min-h-[44px] min-w-[44px] items-center justify-center disabled:opacity-50"
                accessibilityRole="button"
                accessibilityLabel="Close stem export"
              >
                <Text className="font-sans-medium text-sm text-muted-light">Close</Text>
              </AnimatedPressable>
            </View>

            <Text className="mb-3 font-sans text-xs leading-snug text-muted-brown">
              Export every available stem as a ZIP, or download one stem as a WAV.
            </Text>

            <ExportRow
              label="All stems"
              detail="ZIP"
              Icon={FileArchive}
              busy={busyKey === 'all'}
              disabled={busy}
              onPress={onExportAll}
            />

            {stems.map((stem) => (
              <ExportRow
                key={stem}
                label={STEM_LABELS[stem]}
                detail="WAV"
                Icon={FileAudio}
                busy={busyKey === stem}
                disabled={busy}
                onPress={() => onExportStem(stem)}
              />
            ))}
          </View>
        </View>
      </View>
    </Modal>
  )
}

type ExportRowProps = {
  label: string
  detail: string
  Icon: typeof FileAudio
  busy: boolean
  disabled: boolean
  onPress: () => void
}

function ExportRow({ label, detail, Icon, busy, disabled, onPress }: ExportRowProps) {
  return (
    <AnimatedPressable
      onPress={onPress}
      disabled={disabled}
      haptic="light"
      className="mb-1.5 flex min-h-[48px] flex-row items-center gap-3 rounded-xl border border-wood-600/40 bg-wood-800/50 px-3 py-2 disabled:opacity-50"
      accessibilityRole="button"
      accessibilityLabel={`Export ${label} ${detail}`}
      accessibilityState={{ disabled, busy }}
    >
      {busy ? (
        <ActivityIndicator color={colors.amber.light} size="small" />
      ) : (
        <Icon color={colors.amber.accent} size={20} strokeWidth={1.75} />
      )}
      <View className="flex-1">
        <Text className="font-sans-medium text-sm text-cream">{label}</Text>
        <Text className="font-sans text-[11px] text-muted-brown">{detail}</Text>
      </View>
    </AnimatedPressable>
  )
}

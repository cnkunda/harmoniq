import { FileDown, Printer } from 'lucide-react-native'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'

export type TranscriberActionsProps = {
  onPrint: () => void
  onExport: () => void
  exportBusy?: boolean
}

/** Commit 166: Transcriber tier export/print actions for the active score. */
export function TranscriberActions({ onPrint, onExport, exportBusy = false }: TranscriberActionsProps) {
  return (
    <View className="mt-3 flex-row flex-wrap gap-2 px-2">
      <AnimatedPressable
        onPress={onPrint}
        haptic="light"
        className="flex-row items-center gap-2 rounded-lg border border-amber-accent/45 bg-amber-accent/10 px-3 py-2"
        accessibilityRole="button"
        accessibilityLabel="Print the current score"
      >
        <Printer color={colors.amber.accent} size={16} strokeWidth={2} />
        <Text className="font-sans-medium text-xs text-amber-light">Print</Text>
      </AnimatedPressable>
      <AnimatedPressable
        onPress={onExport}
        disabled={exportBusy}
        haptic="light"
        className="flex-row items-center gap-2 rounded-lg border border-wood-600/45 bg-wood-800/45 px-3 py-2 disabled:opacity-50"
        accessibilityRole="button"
        accessibilityLabel="Export MusicXML for the current section"
      >
        <FileDown color={colors.cream} size={16} strokeWidth={2} />
        <Text className="font-sans-medium text-xs text-cream">
          {exportBusy ? 'Exporting…' : 'Export MusicXML'}
        </Text>
      </AnimatedPressable>
    </View>
  )
}

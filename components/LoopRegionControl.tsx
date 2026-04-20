import Slider from '@react-native-community/slider'
import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'
import { clampBarLoopRange } from '@/src/music/barLoopBounds'
import type { TabLoopBarRegion } from '@/types/tabMessage'

type LoopRegionControlProps = {
  barCount: number
  value: TabLoopBarRegion
  onChange: (next: TabLoopBarRegion) => void
  disabled?: boolean
}

/**
 * Two sliders with bar-snapped values and ≥44px row height for touch targets (Slow step).
 */
export function LoopRegionControl({ barCount, value, onChange, disabled }: LoopRegionControlProps) {
  if (barCount < 2) return null

  const clamped = clampBarLoopRange(value.startBarIndex, value.endBarIndexExclusive, barCount)
  const maxStart = barCount - 2
  const span = clamped.endBarIndexExclusive - clamped.startBarIndex

  const applyStart = (raw: number) => {
    const start = Math.round(raw)
    let endEx = clamped.endBarIndexExclusive
    if (endEx <= start) endEx = Math.min(barCount, start + 2)
    onChange(clampBarLoopRange(start, endEx, barCount))
  }

  const applyEnd = (raw: number) => {
    const endEx = Math.round(raw)
    onChange(clampBarLoopRange(clamped.startBarIndex, endEx, barCount))
  }

  return (
    <View className="mt-4 rounded-xl border border-wood-600/40 bg-cream-dark/40 p-3">
      <Text className="font-sans-medium text-sm text-wood-900">Loop region</Text>
      <Text className="mt-1 font-sans text-xs text-muted-brown">
        Handles snap to bar boundaries; playback loops exactly on bar timestamps.
      </Text>

      <View className="mt-3 min-h-[44px] justify-center py-1">
        <Text className="font-sans text-xs text-wood-900">Start bar</Text>
        <Slider
          minimumValue={0}
          maximumValue={maxStart}
          step={1}
          value={clamped.startBarIndex}
          onValueChange={(raw) => applyStart(raw)}
          onSlidingComplete={(raw) => applyStart(raw)}
          minimumTrackTintColor={colors.amber.accent}
          maximumTrackTintColor={colors.wood[600]}
          thumbTintColor={colors.amber.light}
          disabled={disabled}
        />
      </View>

      <View className="mt-2 min-h-[44px] justify-center py-1">
        <Text className="font-sans text-xs text-wood-900">End bar (exclusive)</Text>
        <Slider
          minimumValue={clamped.startBarIndex + 1}
          maximumValue={barCount}
          step={1}
          value={clamped.endBarIndexExclusive}
          onValueChange={(raw) => applyEnd(raw)}
          onSlidingComplete={(raw) => applyEnd(raw)}
          minimumTrackTintColor={colors.amber.accent}
          maximumTrackTintColor={colors.wood[600]}
          thumbTintColor={colors.amber.light}
          disabled={disabled}
        />
      </View>

      <Text className="mt-2 font-mono text-[11px] text-muted-brown">
        Bars {clamped.startBarIndex + 1}–{clamped.endBarIndexExclusive} ({span} bar{span === 1 ? '' : 's'})
      </Text>
    </View>
  )
}

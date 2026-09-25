/** Commit 109: BPM editor — numeric display with fine/coarse adjustment and reset. */

import { Pressable, Text, View } from 'react-native'

import colors from '@/src/constants/colors'

export interface BpmEditorProps {
  bpm: number
  autoBpm: number | null
  onChange: (bpm: number) => void
  onReset: () => void
  disabled?: boolean
}

const COARSE_STEP = 5
const FINE_STEP = 0.5
const MIN_BPM = 30
const MAX_BPM = 240

function AdjustButton({
  label,
  onPress,
  disabled,
}: {
  label: string
  onPress: () => void
  disabled?: boolean
}) {
  return (
    <Pressable
      onPress={() => {
        if (!disabled) onPress()
      }}
      className="h-9 w-9 items-center justify-center rounded-lg"
      style={{
        backgroundColor: colors.wood[700],
        opacity: disabled ? 0.4 : 1,
      }}
    >
      <Text
        style={{
          fontSize: 16,
          fontWeight: '600',
          color: colors.cream,
        }}
      >
        {label}
      </Text>
    </Pressable>
  )
}

/**
 * BPM editor with coarse (±5) and fine (±0.5) adjustment buttons,
 * current BPM display, and "Reset to Auto" button.
 */
export function BpmEditor({ bpm, autoBpm, onChange, onReset, disabled = false }: BpmEditorProps) {
  const canDecrease = bpm > MIN_BPM
  const canIncrease = bpm < MAX_BPM
  const hasAuto = autoBpm !== null && autoBpm > 0
  const isOverridden = hasAuto && Math.abs(bpm - autoBpm!) > 0.1

  return (
    <View className="items-center gap-2">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-muted-brown">
        BPM
      </Text>

      {/* BPM display + fine adjust */}
      <View className="flex-row items-center gap-2">
        <AdjustButton label="−" onPress={() => onChange(Math.max(MIN_BPM, bpm - FINE_STEP))} disabled={disabled || !canDecrease} />
        <AdjustButton label="−+" onPress={() => onChange(Math.max(MIN_BPM, bpm - COARSE_STEP))} disabled={disabled || !canDecrease} />

        <View className="min-w-[64px] items-center rounded-lg border border-wood-600/45 bg-wood-800 px-3 py-1.5">
          <Text className="font-mono text-lg" style={{ color: colors.amber.accent }}>
            {bpm.toFixed(1)}
          </Text>
        </View>

        <AdjustButton label="+" onPress={() => onChange(Math.min(MAX_BPM, bpm + COARSE_STEP))} disabled={disabled || !canIncrease} />
        <AdjustButton label="++" onPress={() => onChange(Math.min(MAX_BPM, bpm + FINE_STEP))} disabled={disabled || !canIncrease} />
      </View>

      {/* Reset to auto */}
      {isOverridden && (
        <Pressable
          onPress={() => {
            if (!disabled && hasAuto) {
              onChange(autoBpm!)
              onReset()
            }
          }}
          className="rounded-full border border-wood-600/45 bg-wood-800 px-3 py-1"
        >
          <Text className="font-sans text-xs" style={{ color: colors.amber.light }}>
            Reset to Auto ({autoBpm!.toFixed(0)})
          </Text>
        </Pressable>
      )}
    </View>
  )
}

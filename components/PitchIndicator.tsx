import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated'

import colors from '@/src/constants/colors'
import { CHROMATIC_NOTE_NAMES } from '@/src/music/noteNames'
import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'

export interface PitchIndicatorProps {
  note?: string
  cents?: number
  isActive?: boolean
  targetMidi?: number
  /** Upcoming tab note (one event behind current for a simple preview). */
  nextTargetMidi?: number | null
  /** Latest closed beat result — drives transient ladder flash. */
  windowResult?: NoteResultLabel | null
  /** Increment to retrigger flash even when result repeats. */
  windowFlashToken?: number
}

function midiToHz(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

/**
 * Scientific pitch notation with middle C = MIDI 60 (C4).
 * Some manufacturers label middle C as C3 (e.g. Yamaha) — this app uses the MIDI convention.
 */
export function midiToScientificPitchName(midi: number): string {
  const rounded = Math.round(midi)
  const octave = Math.floor(rounded / 12) - 1
  return `${CHROMATIC_NOTE_NAMES[((rounded % 12) + 12) % 12]}${octave}`
}

/** Sage / amber / terracotta flash per closed beat — shared with Play pitch ladder (PRIORITIES §49). */
export const PITCH_WINDOW_FLASH_BG: Partial<Record<NoteResultLabel, string>> = {
  hit: colors.success,
  close: colors.amber.accent,
  miss: colors.danger,
  vibrato: colors.amber.light,
  ignored: colors.wood[600],
}

export function PitchIndicator({
  note,
  cents,
  isActive,
  targetMidi,
  nextTargetMidi,
  windowResult,
  windowFlashToken = 0,
}: PitchIndicatorProps) {
  const hz = typeof targetMidi === 'number' && Number.isFinite(targetMidi) ? midiToHz(targetMidi) : null
  const flashOpacity = useSharedValue(0)

  useEffect(() => {
    if (!windowResult || windowResult === 'ignored' || windowFlashToken <= 0) return
    flashOpacity.value = 0
    flashOpacity.value = withSequence(
      withTiming(0.55, { duration: 70 }),
      withTiming(0, { duration: 420 }),
    )
  }, [windowFlashToken, windowResult, flashOpacity])

  const flashStyle = useAnimatedStyle(() => ({
    opacity: flashOpacity.value,
  }))

  const flashColor =
    windowResult && windowResult !== 'ignored'
      ? (PITCH_WINDOW_FLASH_BG[windowResult] ?? colors.wood[600])
      : colors.wood[600]

  const activeSci =
    typeof targetMidi === 'number' && Number.isFinite(targetMidi) ? midiToScientificPitchName(targetMidi) : null
  const nextSci =
    typeof nextTargetMidi === 'number' && Number.isFinite(nextTargetMidi)
      ? midiToScientificPitchName(nextTargetMidi)
      : null

  return (
    <View className="relative overflow-hidden rounded-lg border border-dashed border-wood-600 p-4">
      {windowResult && windowResult !== 'ignored' ? (
        <Animated.View
          pointerEvents="none"
          style={[
            {
              position: 'absolute',
              left: 0,
              right: 0,
              top: 0,
              bottom: 0,
              borderRadius: 8,
              backgroundColor: flashColor,
            },
            flashStyle,
          ]}
        />
      ) : null}
      <Text className="font-mono text-amber-accent">Pitch ladder</Text>
      <Text className="mt-1 font-sans text-xs text-muted-brown">
        target: {hz != null ? `${hz.toFixed(1)} Hz` : '—'} {note ? `| note: ${note}` : ''}{' '}
        {typeof cents === 'number' ? `| cents: ${Math.round(cents)}` : ''} {isActive ? '| active' : ''}
      </Text>
      {activeSci ? (
        <Text className="mt-0.5 font-sans text-[10px] text-muted-brown">MIDI name: {activeSci}</Text>
      ) : null}
      {nextSci ? (
        <Text className="mt-0.5 font-sans text-[10px] text-muted-brown/90">Next: {nextSci}</Text>
      ) : null}
      <View className="relative mt-2 h-1.5 w-full rounded-full bg-wood-600/40">
        <View className="h-1.5 w-1/2 rounded-full bg-amber-accent/80" />
      </View>
    </View>
  )
}

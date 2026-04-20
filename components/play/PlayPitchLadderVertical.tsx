import { useEffect } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withSequence, withTiming } from 'react-native-reanimated'

import { midiToScientificPitchName, PITCH_WINDOW_FLASH_BG } from '@/components/PitchIndicator'
import colors from '@/src/constants/colors'
import { hitInnerThresholdCents, type NoteResultLabel } from '@/src/session/noteAccuracyBeats'

type PlayPitchLadderVerticalProps = {
  /** When true, no outer card chrome (sits inside playback strip scoring column). */
  embedded?: boolean
  /** Optional layout classes (e.g. max width on large screens). */
  className?: string
  cents: number | null | undefined
  isActive: boolean
  adaptedCentsTolerance: number
  targetMidi: number
  nextTargetMidi?: number | null
  /** Latest closed beat — transient full-card flash (matches PitchIndicator). */
  windowResult?: NoteResultLabel | null
  windowFlashToken?: number
}

/** Short track so the card sits near the height of the sibling pitch/beat panel on md+ layouts. */
const TRACK_H = 118
const TRACK_W = 44

/**
 * Vertical cents ladder (-50..+50) with compact status copy (Perfect / Close / Sharp / Flat).
 */
export function PlayPitchLadderVertical({
  embedded = false,
  className,
  cents,
  isActive,
  adaptedCentsTolerance,
  targetMidi,
  nextTargetMidi,
  windowResult,
  windowFlashToken = 0,
}: PlayPitchLadderVerticalProps) {
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

  const innerTol = hitInnerThresholdCents(adaptedCentsTolerance)
  const clamped =
    cents != null && Number.isFinite(cents) ? Math.max(-50, Math.min(50, cents)) : 0
  /** 0 = top (+50¢), 100 = bottom (-50¢), 50 = center */
  const positionPct = 50 - clamped
  const targetSci = Number.isFinite(targetMidi) ? midiToScientificPitchName(targetMidi) : '—'
  const nextSci =
    nextTargetMidi != null && Number.isFinite(nextTargetMidi)
      ? midiToScientificPitchName(nextTargetMidi)
      : null

  let statusTitle = 'Waiting…'
  let statusSub = 'Play to see pitch feedback'
  let statusTone = 'text-muted-brown'

  if (isActive && cents != null && Number.isFinite(cents)) {
    const a = Math.abs(cents)
    if (a <= innerTol) {
      statusTitle = 'Perfect!'
      statusSub = 'Great pitch accuracy'
      statusTone = 'text-success'
    } else if (a <= adaptedCentsTolerance) {
      statusTitle = 'Close'
      statusSub = `Adjust ${cents > 0 ? 'down' : 'up'} ${Math.abs(Math.round(cents))} cents`
      statusTone = 'text-amber-accent'
    } else {
      statusTitle = cents > 0 ? 'Sharp' : 'Flat'
      statusSub = `Adjust ${cents > 0 ? 'down' : 'up'} ${Math.abs(Math.round(cents))} cents`
      statusTone = 'text-danger'
    }
  }

  const rootClass = embedded
    ? [
        'relative min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden p-0 lg:ml-0.5 lg:min-w-[148px] lg:border-l lg:border-wood-600/20 lg:pl-3 lg:pt-0.5',
        className ?? '',
      ]
        .join(' ')
        .trim()
    : [
        'relative w-full shrink-0 flex-col overflow-hidden rounded-2xl border border-wood-600/45 bg-cream-dark/55 p-3 md:max-w-md md:self-start',
        className ?? '',
      ]
        .join(' ')
        .trim()

  const flashRadius = embedded ? 12 : 16

  return (
    <View className={rootClass}>
      {windowResult && windowResult !== 'ignored' ? (
        <Animated.View
          pointerEvents="none"
          style={[
            StyleSheet.absoluteFillObject,
            { borderRadius: flashRadius, backgroundColor: flashColor },
            flashStyle,
          ]}
        />
      ) : null}
      {embedded ? (
        <View className="mb-1 flex-row items-center justify-end">
          <Text className={`font-mono text-xs ${isActive && cents != null ? 'text-wood-900' : 'text-muted-brown'}`}>
            {isActive && cents != null && Number.isFinite(cents)
              ? `${cents >= 0 ? '+' : ''}${Math.round(cents)}¢`
              : '—'}
          </Text>
        </View>
      ) : (
        <View className="flex-row items-center justify-between gap-2">
          <Text className="shrink font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
            Live pitch vs target
          </Text>
          <Text className={`font-mono text-sm ${isActive && cents != null ? 'text-wood-900' : 'text-muted-brown'}`}>
            {isActive && cents != null && Number.isFinite(cents)
              ? `${cents >= 0 ? '+' : ''}${Math.round(cents)}¢`
              : '—'}
          </Text>
        </View>
      )}
      <View
        className={
          embedded
            ? 'mt-0 min-h-0 flex-1 flex-row items-stretch gap-2.5'
            : 'mt-2.5 flex-row items-stretch gap-2.5'
        }
      >
        <View
          style={embedded ? { width: TRACK_W } : { width: TRACK_W, height: TRACK_H }}
          className="shrink-0 self-stretch overflow-hidden rounded-lg border border-wood-600/35 bg-wood-900/10"
        >
          <View
            className="absolute left-0 right-0 bg-success/15"
            style={{ top: '35%', height: '30%' }}
          />
          <View className="absolute left-0 right-0 border-t border-wood-600/40" style={{ top: '50%' }} />
          <Text className="absolute right-0.5 top-0.5 font-mono text-[9px] text-muted-brown">+50</Text>
          <Text className="absolute right-0.5 top-[46%] font-mono text-[9px] text-muted-brown">0</Text>
          <Text className="absolute bottom-0.5 right-0.5 font-mono text-[9px] text-muted-brown">-50</Text>
          {isActive && cents != null ? (
            <View
              className="absolute left-1 right-1 z-10 rounded-full bg-amber-accent"
              style={{ height: 10, top: `${positionPct}%`, marginTop: -5 }}
            />
          ) : null}
        </View>
        <View className="min-w-0 flex-1 justify-center py-0.5">
          <Text className="font-mono text-[11px] text-wood-900">Target · {targetSci}</Text>
          {nextSci ? (
            <Text className="mt-0.5 font-mono text-[10px] text-muted-brown">Was · {nextSci}</Text>
          ) : null}
          <Text className={`mt-2 font-sans text-xl font-bold leading-tight ${statusTone}`}>{statusTitle}</Text>
          <Text className="mt-0.5 font-sans text-xs leading-snug text-muted-brown">{statusSub}</Text>
        </View>
      </View>
    </View>
  )
}

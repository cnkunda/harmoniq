import { useEffect, useMemo } from 'react'
import { Pressable, Text, View } from 'react-native'
import Animated, {
  Easing,
  interpolate,
  interpolateColor,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated'

import { spring } from '@/src/constants/animations'
import colors from '@/src/constants/colors'
import { NUM_FRETS, OPEN_MIDI_BY_ROW, inferMidiFromNoteSelection, resolveFretCell } from '@/src/music/fretboardCell'

export { inferMidiFromNoteSelection, resolveFretCell } from '@/src/music/fretboardCell'

export type FretboardLastCellResult = {
  row: number
  fret: number
  result: 'hit' | 'close' | 'miss'
}

type FretboardDiagramProps = {
  keyLabel: string
  positionLabel: string
  capoText: string
  selectedNote?: {
    string?: number
    fret?: number
    midi?: number
  } | null
  pulseKey?: number
  /** Pitch classes 0–11 to outline subtly (Jam scale overlay). */
  scalePitchClasses?: readonly number[] | null
  /** Optional: tapping a map cell selects that note (used by Study/Play). */
  onSelectNote?: (note: { string: number; fret: number; midi: number }) => void
  /** Last scored beat — brief tint on the matching string/fret cell (Play). */
  lastCellResult?: FretboardLastCellResult | null
}

/** Warm HSL peak keyed by pitch class so each perception note reads as a distinct flash (Study B3). */
function flashPeakColorForMidi(midi: number | null): string {
  if (midi == null || !Number.isFinite(midi)) return '#F5ECD8'
  const pc = ((Math.round(midi) % 12) + 12) % 12
  const hue = 26 + pc * 2.2
  return `hsl(${hue}, 76%, 76%)`
}

/**
 * Remount via `key={pulseKey}` from parent so each `noteEvent` replays scale + color pulse in sync with playback.
 */
function SelectedMarker({ flashMidi }: { flashMidi: number | null }) {
  const scale = useSharedValue(1)
  const colorPulse = useSharedValue(0)
  const peakFill = useMemo(() => flashPeakColorForMidi(flashMidi), [flashMidi])

  useEffect(() => {
    scale.value = 1
    colorPulse.value = 0
    scale.value = withSequence(withSpring(1.45, spring.snappy), withSpring(1, spring.gentle))
    colorPulse.value = withSequence(
      withTiming(1, { duration: 100, easing: Easing.out(Easing.quad) }),
      withTiming(0, { duration: 340, easing: Easing.in(Easing.quad) }),
    )
  }, [scale, colorPulse, peakFill])

  const dotStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    backgroundColor: interpolateColor(colorPulse.value, [0, 1], [colors.amber.accent, peakFill]),
    borderColor: interpolateColor(colorPulse.value, [0, 1], [colors.amber.light, '#FFFAF0']),
  }))

  const ringStyle = useAnimatedStyle(() => ({
    opacity: interpolate(colorPulse.value, [0, 0.15, 1], [0, 0.55, 0.9]),
    transform: [{ scale: interpolate(colorPulse.value, [0, 1], [0.85, 1.75]) }],
  }))

  // Avoid NativeWind `className` on Animated.View — on web it can override `transform` and kill the pulse.
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center', width: 28, height: 28 }}>
      <Animated.View
        style={[
          ringStyle,
          {
            position: 'absolute',
            width: 20,
            height: 20,
            borderRadius: 10,
            borderWidth: 2,
            borderColor: colors.amber.light,
          },
        ]}
      />
      <Animated.View
        style={[
          dotStyle,
          {
            width: 16,
            height: 16,
            borderRadius: 8,
            borderWidth: 2,
            shadowColor: '#000',
            shadowOpacity: 0.22,
            shadowRadius: 3,
            shadowOffset: { width: 0, height: 1 },
          },
        ]}
      />
    </View>
  )
}

/**
 * Six strings × nut + 12 frets; selected AlphaTab note renders above dot pattern.
 */
function scaleHighlightActive(
  scalePitchClasses: readonly number[] | null | undefined,
  stringIdx: number,
  fret: number,
): boolean {
  if (!scalePitchClasses || scalePitchClasses.length === 0) return false
  const midi = OPEN_MIDI_BY_ROW[stringIdx]! + fret
  const pc = ((midi % 12) + 12) % 12
  return scalePitchClasses.includes(pc)
}

function cellMatchesDiagramCol(
  cellFret: number,
  col: number,
): boolean {
  return cellFret <= NUM_FRETS ? cellFret === col : col === NUM_FRETS
}

export function FretboardDiagram({
  keyLabel,
  positionLabel,
  capoText,
  selectedNote,
  pulseKey = 0,
  scalePitchClasses = null,
  onSelectNote,
  lastCellResult = null,
}: FretboardDiagramProps) {
  const cell = selectedNote ? resolveFretCell(selectedNote) : null
  const flashMidi = selectedNote ? inferMidiFromNoteSelection(selectedNote) : null

  return (
    <View className="mt-3 rounded-xl border border-wood-600/45 bg-cream-dark/45 p-3">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Position map</Text>
      <Text className="mt-1 font-sans text-xs text-wood-900">
        {keyLabel} · {positionLabel}
      </Text>
      <Text className="mt-0.5 font-sans text-[11px] text-muted-brown">{capoText}</Text>

      <View className="mt-3">
        <View className="flex-row border-b border-wood-600/30 pb-1">
          <View className="w-7" />
          {Array.from({ length: NUM_FRETS + 1 }).map((_, col) => (
            <View key={`h-${col}`} className="flex-1 items-center">
              <Text className="font-mono text-[9px] text-muted-brown">{col === 0 ? 'O' : col}</Text>
            </View>
          ))}
        </View>

        {Array.from({ length: 6 }).map((_, stringIdx) => (
          <View key={`s-${stringIdx}`} className="relative flex-row items-center border-b border-wood-600/15 py-1">
            <Text className="w-7 font-mono text-[9px] text-muted-brown">{stringIdx + 1}</Text>
            {Array.from({ length: NUM_FRETS + 1 }).map((__, col) => {
              const fret = col
              const underlay = (stringIdx + col) % 4 === 0
              const selected =
                cell != null &&
                cell.row === stringIdx &&
                cellMatchesDiagramCol(cell.fret, fret)
              const feedbackHere =
                lastCellResult != null &&
                lastCellResult.row === stringIdx &&
                cellMatchesDiagramCol(lastCellResult.fret, fret)
              const feedbackRing =
                feedbackHere && lastCellResult
                  ? lastCellResult.result === 'hit'
                    ? 'border-success bg-success/35'
                    : lastCellResult.result === 'close'
                      ? 'border-amber-accent bg-amber-accent/30'
                      : 'border-danger bg-danger/35'
                  : ''
              const scaleOn = scaleHighlightActive(scalePitchClasses, stringIdx, fret)
              const midi = OPEN_MIDI_BY_ROW[stringIdx]! + fret
              return (
                <Pressable
                  key={`c-${stringIdx}-${col}`}
                  onPress={() => onSelectNote?.({ string: stringIdx + 1, fret, midi })}
                  disabled={!onSelectNote}
                  className="relative flex-1 items-center justify-center py-0.5"
                  accessibilityRole={onSelectNote ? 'button' : undefined}
                  accessibilityLabel={onSelectNote ? `String ${stringIdx + 1}, fret ${fret}` : undefined}
                >
                  {feedbackHere && lastCellResult ? (
                    <View className={`absolute z-[15] h-5 w-5 rounded-full border-2 ${feedbackRing}`} />
                  ) : null}
                  {scaleOn && !selected ? (
                    <View className="absolute z-10 h-4 w-4 rounded-full border border-emerald-400/55 bg-emerald-500/15" />
                  ) : null}
                  <View
                    className={`h-3 w-3 rounded-full ${underlay ? 'bg-amber-accent/25' : 'bg-wood-600/15'} ${selected ? 'opacity-40' : ''}`}
                  />
                  {selected ? (
                    <View className="absolute inset-0 z-20 items-center justify-center">
                      <SelectedMarker key={pulseKey} flashMidi={flashMidi} />
                    </View>
                  ) : null}
                </Pressable>
              )
            })}
          </View>
        ))}
      </View>

      <Text className="mt-2 font-mono text-[10px] text-muted-brown">
        {cell
          ? `Selected · string ${cell.row + 1} (tab) · fret ${cell.fret} · pulse #${pulseKey}`
          : 'Tap a note in the score to highlight a fret.'}
      </Text>
    </View>
  )
}

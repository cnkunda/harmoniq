import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withSequence, withSpring } from 'react-native-reanimated'

import { spring } from '@/src/constants/animations'
import { NUM_FRETS, OPEN_MIDI_BY_ROW, resolveFretCell } from '@/src/music/fretboardCell'

export { inferMidiFromNoteSelection, resolveFretCell } from '@/src/music/fretboardCell'

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
}

function SelectedMarker({ pulseKey }: { pulseKey: number }) {
  const scale = useSharedValue(1)

  useEffect(() => {
    scale.value = withSequence(withSpring(1.45, spring.snappy), withSpring(1, spring.gentle))
  }, [pulseKey, scale])

  const style = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }))

  return (
    <Animated.View
      style={style}
      className="absolute z-20 h-4 w-4 rounded-full border-2 border-amber-light bg-amber-accent shadow-md"
    />
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

export function FretboardDiagram({
  keyLabel,
  positionLabel,
  capoText,
  selectedNote,
  pulseKey = 0,
  scalePitchClasses = null,
}: FretboardDiagramProps) {
  const cell = selectedNote ? resolveFretCell(selectedNote) : null

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
                (cell.fret <= NUM_FRETS ? cell.fret === fret : fret === NUM_FRETS)
              const scaleOn = scaleHighlightActive(scalePitchClasses, stringIdx, fret)
              return (
                <View key={`c-${stringIdx}-${col}`} className="relative flex-1 items-center justify-center py-0.5">
                  {scaleOn && !selected ? (
                    <View className="absolute z-10 h-4 w-4 rounded-full border border-emerald-400/55 bg-emerald-500/15" />
                  ) : null}
                  <View
                    className={`h-3 w-3 rounded-full ${underlay ? 'bg-amber-accent/25' : 'bg-wood-600/15'} ${selected ? 'opacity-40' : ''}`}
                  />
                  {selected ? (
                    <View className="absolute inset-0 z-20 items-center justify-center">
                      <SelectedMarker pulseKey={pulseKey} />
                    </View>
                  ) : null}
                </View>
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

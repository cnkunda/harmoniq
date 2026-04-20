import { useEffect, useMemo } from 'react'
import { Platform, Pressable, Text, View } from 'react-native'
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
import type { FretboardTunerState } from '@/src/session/useFretboardTuner'
import { pitchClassLabelFromMidi } from '@/src/music/noteNames'
import type { FretboardOverlayMode } from '@/src/utils/fretboardShareState'

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
  /** Overlay labels for learning aids (off by default to avoid clutter). */
  overlayMode?: FretboardOverlayMode
  /** Root pitch class (0-11), used for scale-degree overlays. */
  degreeRootPitchClass?: number | null
  /** Web-only shortcut input (keyboard rows map to fret positions). */
  enableKeyboardInput?: boolean
  /** Optional compact overlay mode controls in header action row. */
  showOverlayControls?: boolean
  onOverlayModeChange?: (mode: FretboardOverlayMode) => void
  /** Optional share-link action in header action row. */
  showCopyShare?: boolean
  onCopyShareLink?: () => void
  /** Optional top-right tuner toggle on the fretboard header. */
  showTuneControl?: boolean
  tuneActive?: boolean
  tuneDisabled?: boolean
  tuneCalibrating?: boolean
  onToggleTune?: () => void
  onCalibrateTune?: () => void
  tunerState?: FretboardTunerState | null
  /** Warm-up / curriculum: highlight fixed cells (amber vs success rings). */
  fretGuideCells?: ReadonlyArray<{ string: number; fret: number; variant: 'primary' | 'secondary' }> | null
  /** When set, replaces default footer hint when nothing is selected. */
  fretGuideFooterHint?: string | null
}

const SCALE_DEGREE_LABELS: Record<number, string> = {
  0: '1',
  1: 'b2',
  2: '2',
  3: 'b3',
  4: '3',
  5: '4',
  6: 'b5',
  7: '5',
  8: '#5',
  9: '6',
  10: 'b7',
  11: '7',
}

const KEYBOARD_ROWS = ['1234567890-=', 'qwertyuiop[]', "asdfghjkl;'", 'zxcvbnm,./'] as const

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

function overlayLabelForCell(
  overlayMode: FretboardOverlayMode,
  midi: number,
  degreeRootPitchClass: number | null,
): string | null {
  if (overlayMode === 'off') return null
  if (overlayMode === 'note_names') return pitchClassLabelFromMidi(midi)
  if (degreeRootPitchClass == null) return null
  const pc = ((Math.round(midi) % 12) + 12) % 12
  const iv = (pc - degreeRootPitchClass + 12) % 12
  return SCALE_DEGREE_LABELS[iv] ?? null
}

function guideVariantAtCell(
  fretGuideCells: ReadonlyArray<{ string: number; fret: number; variant: 'primary' | 'secondary' }> | null | undefined,
  stringIdx: number,
  diagramCol: number,
): 'primary' | 'secondary' | null {
  if (!fretGuideCells?.length) return null
  for (const gc of fretGuideCells) {
    if (gc.string === stringIdx + 1 && cellMatchesDiagramCol(gc.fret, diagramCol)) {
      return gc.variant
    }
  }
  return null
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
  overlayMode = 'off',
  degreeRootPitchClass = null,
  enableKeyboardInput = false,
  showOverlayControls = false,
  onOverlayModeChange,
  showCopyShare = false,
  onCopyShareLink,
  showTuneControl = false,
  tuneActive = false,
  tuneDisabled = false,
  tuneCalibrating = false,
  onToggleTune,
  onCalibrateTune,
  tunerState = null,
  fretGuideCells = null,
  fretGuideFooterHint = null,
}: FretboardDiagramProps) {
  const cell = selectedNote ? resolveFretCell(selectedNote) : null
  const flashMidi = selectedNote ? inferMidiFromNoteSelection(selectedNote) : null

  useEffect(() => {
    if (!onSelectNote || !enableKeyboardInput || Platform.OS !== 'web') return
    const handler = (evt: KeyboardEvent) => {
      const target = evt.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
      // Do not steal browser shortcuts (Ctrl/Meta/Alt + key still reports the base character).
      if (evt.ctrlKey || evt.metaKey || evt.altKey) return
      const key = evt.key.toLowerCase()
      let rowIndex = -1
      let fret = -1
      for (let i = 0; i < KEYBOARD_ROWS.length; i += 1) {
        const idx = KEYBOARD_ROWS[i].indexOf(key)
        if (idx >= 0) {
          rowIndex = i
          fret = idx
          break
        }
      }
      if (rowIndex < 0 || fret < 0 || fret > NUM_FRETS) return
      // Musicca-style behavior: hold Shift to access upper strings from the top rows.
      let stringIdx = 5 - rowIndex
      if (evt.shiftKey && rowIndex <= 1) {
        stringIdx = rowIndex === 0 ? 1 : 0
      }
      if (stringIdx < 0 || stringIdx > 5) return
      evt.preventDefault()
      onSelectNote({
        string: stringIdx + 1,
        fret,
        midi: OPEN_MIDI_BY_ROW[stringIdx]! + fret,
      })
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [enableKeyboardInput, onSelectNote])

  return (
    <View className="mt-3 rounded-xl border border-wood-600/45 bg-cream-dark/45 p-3">
      <View className="flex-row items-start justify-between gap-2">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Position map</Text>
        {showTuneControl || showOverlayControls || showCopyShare ? (
          <View className="max-w-[76%] flex-row flex-wrap items-center justify-end gap-1.5">
            {tuneActive && onCalibrateTune ? (
              <Pressable
                onPress={onCalibrateTune}
                className="rounded-full border border-wood-600/45 bg-cream-dark/50 px-2.5 py-1"
                accessibilityRole="button"
                accessibilityLabel="Calibrate tuner noise floor"
              >
                <Text className="font-mono text-[9px] text-wood-900">{tuneCalibrating ? 'Cal…' : 'Cal'}</Text>
              </Pressable>
            ) : null}
            {showTuneControl ? (
              <Pressable
                onPress={onToggleTune}
                disabled={tuneDisabled}
                className={`rounded-full border px-3 py-1 ${tuneActive ? 'border-success bg-success/25' : 'border-wood-600/45 bg-cream-dark/50'} ${tuneDisabled ? 'opacity-45' : ''}`}
                accessibilityRole="button"
                accessibilityLabel={tuneActive ? 'Disable fretboard tuner' : 'Enable fretboard tuner'}
              >
                <Text className={`font-sans text-[11px] ${tuneActive ? 'text-wood-900' : 'text-muted-brown'}`}>
                  {tuneActive ? 'Tune on' : 'Tune'}
                </Text>
              </Pressable>
            ) : null}
            {showOverlayControls
              ? ([
                  { mode: 'off' as const, label: 'Overlay off' },
                  { mode: 'note_names' as const, label: 'Note names' },
                  { mode: 'scale_degrees' as const, label: 'Scale degrees' },
                ] as const).map(({ mode, label }) => (
                  <Pressable
                    key={mode}
                    onPress={() => onOverlayModeChange?.(mode)}
                    disabled={!onOverlayModeChange}
                    className={`rounded-full border px-3 py-1 ${
                      overlayMode === mode ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/50'
                    } ${onOverlayModeChange ? '' : 'opacity-50'}`}
                    accessibilityRole="button"
                    accessibilityLabel={label}
                    accessibilityState={{ selected: overlayMode === mode }}
                  >
                    <Text className={`font-sans text-[11px] ${overlayMode === mode ? 'text-wood-900' : 'text-muted-brown'}`}>
                      {label}
                    </Text>
                  </Pressable>
                ))
              : null}
            {showCopyShare ? (
              <Pressable
                onPress={onCopyShareLink}
                disabled={!onCopyShareLink}
                className={`rounded-full border border-wood-600/45 bg-cream-dark/50 px-3 py-1 ${onCopyShareLink ? '' : 'opacity-50'}`}
                accessibilityRole="button"
                accessibilityLabel="Copy share link"
              >
                <Text className="font-sans text-[11px] text-wood-900">Copy share link</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </View>
      <Text className="mt-1 font-sans text-xs text-wood-900">
        {keyLabel} · {positionLabel}
      </Text>
      <Text className="mt-0.5 font-sans text-[11px] text-muted-brown">{capoText}</Text>
      {tuneActive && tunerState ? (
        <View className="mt-2 rounded-lg border border-wood-600/35 bg-ivory/35 px-2.5 py-2">
          <Text className="font-mono text-[11px] text-wood-900">
            {tunerState.noteName || '—'} · {typeof tunerState.cents === 'number' ? `${Math.round(tunerState.cents)}¢` : '—'} ·{' '}
            {tunerState.hz != null ? `${tunerState.hz.toFixed(1)} Hz` : 'no pitch'}
          </Text>
          <Text className={`mt-1 font-sans text-[11px] ${tunerState.inTune ? 'text-success' : 'text-muted-brown'}`}>
            {tunerState.statusText}
          </Text>
        </View>
      ) : null}

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
              const overlayLabel = overlayLabelForCell(overlayMode, midi, degreeRootPitchClass)
              const guideVariant = guideVariantAtCell(fretGuideCells, stringIdx, fret)
              const guideRingClass =
                guideVariant === 'primary'
                  ? 'border-amber-accent bg-amber-accent/30'
                  : guideVariant === 'secondary'
                    ? 'border-success bg-success/35'
                    : ''
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
                  {guideVariant && guideRingClass && !selected ? (
                    <View className={`absolute z-[11] h-5 w-5 rounded-full border-2 ${guideRingClass}`} />
                  ) : null}
                  {scaleOn && !selected ? (
                    <View className="absolute z-10 h-4 w-4 rounded-full border border-emerald-400/55 bg-emerald-500/15" />
                  ) : null}
                  <View
                    className={`h-3 w-3 rounded-full ${underlay ? 'bg-amber-accent/25' : 'bg-wood-600/15'} ${selected ? 'opacity-40' : ''}`}
                  />
                  {overlayLabel ? (
                    <Text className="absolute z-[12] font-mono text-[8px] text-wood-900/80">{overlayLabel}</Text>
                  ) : null}
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
          : fretGuideFooterHint?.trim() || 'Tap a note in the score to highlight a fret.'}
      </Text>
      {enableKeyboardInput && Platform.OS === 'web' ? (
        <Text className="mt-1 font-sans text-[10px] text-muted-brown">
          Keyboard: rows `1-4` map to lower strings; hold Shift on top rows for strings 1-2.
        </Text>
      ) : null}
    </View>
  )
}

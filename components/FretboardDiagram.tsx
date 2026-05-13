import { LinearGradient } from 'expo-linear-gradient'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Platform, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native'
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
import { pitchClassLabelFromMidi } from '@/src/music/noteNames'
import type { FretboardTunerState } from '@/src/session/useFretboardTuner'
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
  /** Optional Orient/Hint button for technique demonstration clips. */
  showOrientControl?: boolean
  orientActive?: boolean
  onToggleOrient?: () => void
  orientClipUrl?: string | null
  orientAnnotation?: string | null
  orientIsPlaying?: boolean
  onToggleOrientPlayback?: () => void
  /** Warm-up / curriculum: highlight fixed cells (amber vs success rings). Finger 1-4 optional for color coding. */
  fretGuideCells?: ReadonlyArray<{ string: number; fret: number; variant: 'primary' | 'secondary'; finger?: 1 | 2 | 3 | 4 }> | null
  /** Active sequence index for animated warmup exercise highlighting */
  activeGuideIndex?: number | null
  /** Chord shape cells to highlight on the fretboard (for intelligent display). */
  chordCells?: ReadonlyArray<{ string: number; fret: number; interval?: number }> | null
  /** When set, replaces default footer hint when nothing is selected. */
  fretGuideFooterHint?: string | null
  /** Optional pitch-ladder demo (e.g. warm-up); shows an “Example” pill like Tune. */
  pitchLadderSlot?: ReactNode
  /** When `pitchLadderSlot` is set, initial expanded state (default `true`). */
  pitchLadderDefaultExpanded?: boolean
  /** Fretboard display mode for intelligent chord/solo visualization. */
  fretboardMode?: 'auto' | 'chords' | 'solo' | 'both'
  /** Callback when fretboard mode changes. */
  onFretboardModeChange?: (mode: 'auto' | 'chords' | 'solo' | 'both') => void
  /** Chord voicing compactness preference. */
  voicingMode?: 'full' | 'compact'
  /** Callback when voicing mode changes. */
  onVoicingModeChange?: (mode: 'full' | 'compact') => void
}

/** Finger colors matching the shared Fretboard component style */
const FINGER_COLORS: Record<number, { fill: string; border: string }> = {
  1: { fill: '#60A5FA', border: '#3B82F6' }, // Index - blue
  2: { fill: '#34D399', border: '#10B981' }, // Middle - green
  3: { fill: '#FBBF24', border: '#F59E0B' }, // Ring - yellow
  4: { fill: '#F87171', border: '#EF4444' }, // Pinky - red
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

/** Matches typical dot inlays (fret numbers are diagram columns: 0 = nut). */
const SINGLE_INLAY_FRETS = new Set([3, 5, 7, 9])

const NUT_COLUMN_WIDTH = 44

const OPEN_STRING_NOTE_LETTERS = OPEN_MIDI_BY_ROW.map((midi) => pitchClassLabelFromMidi(midi))

function fretInlayKind(
  fret: number,
  stringIdx: number,
): 'single' | 'doubleUpper' | 'doubleLower' | null {
  if (fret === 12) {
    if (stringIdx === 0) return 'doubleUpper'
    if (stringIdx === 5) return 'doubleLower'
    return null
  }
  if (SINGLE_INLAY_FRETS.has(fret) && stringIdx === 2) return 'single'
  return null
}

function stringLineThicknessPx(stringIdx: number): number {
  return 1 + stringIdx * 0.38
}

/** Web-only wound-string look (`repeating-linear-gradient` + shadow). */
function stringLineWebBackground(heightPx: number): ViewStyle {
  const mid = Math.max(1, Math.round(heightPx / 2))
  return {
    width: '100%',
    height: heightPx,
    borderRadius: heightPx / 2,
    backgroundImage: `repeating-linear-gradient(90deg, #a8a29e 0px, #f5f5f4 ${mid}px, #78716c ${mid + 2}px, #e7e5e4 ${mid + 4}px, #a8a29e ${mid + 6}px)`,
    boxShadow: '0 1px 2px rgba(0,0,0,0.14)',
  } as ViewStyle
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
  fretGuideCells: ReadonlyArray<{ string: number; fret: number; variant: 'primary' | 'secondary'; finger?: 1 | 2 | 3 | 4 }> | null | undefined,
  stringIdx: number,
  diagramCol: number,
): { variant: 'primary' | 'secondary'; finger?: 1 | 2 | 3 | 4 } | null {
  if (!fretGuideCells?.length) return null
  for (const gc of fretGuideCells) {
    if (gc.string === stringIdx + 1 && cellMatchesDiagramCol(gc.fret, diagramCol)) {
      return { variant: gc.variant, finger: gc.finger }
    }
  }
  return null
}

/**
 * Guide marker with finger-color coding for warmup exercise display.
 * Shows finger number or overlay label inside colored circle with pulse animation when active.
 */
function GuideMarker({
  finger,
  isActive,
  overlayLabel,
}: {
  finger?: 1 | 2 | 3 | 4
  isActive?: boolean
  overlayLabel?: string | null | undefined
}) {
  const colors = finger ? FINGER_COLORS[finger] : { fill: '#D4A574', border: '#B8956A' }
  const scale = useSharedValue(1)
  const pulseAnim = useSharedValue(0)

  useEffect(() => {
    scale.value = 1
    pulseAnim.value = 0
    if (isActive) {
      scale.value = withSequence(withSpring(1.25, spring.snappy), withSpring(1.1, spring.gentle))
      pulseAnim.value = withSequence(
        withTiming(1, { duration: 150, easing: Easing.out(Easing.quad) }),
        withTiming(0, { duration: 300, easing: Easing.in(Easing.quad) }),
      )
    }
  }, [isActive, scale, pulseAnim])

  const containerStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }))

  const ringStyle = useAnimatedStyle(() => ({
    opacity: isActive ? interpolate(pulseAnim.value, [0, 0.5, 1], [0.6, 0.9, 0.6]) : 0.4,
    transform: [{ scale: isActive ? interpolate(pulseAnim.value, [0, 1], [1, 1.4]) : 1 }],
  }))

  // Determine what to display: overlay label takes precedence over finger number
  const displayContent = overlayLabel ?? (finger ? finger.toString() : null)
  // Scale font size based on content length
  const fontSize = overlayLabel && overlayLabel.length > 1 ? 8 : 10

  return (
    <View style={{ alignItems: 'center', justifyContent: 'center', width: 28, height: 28 }}>
      <Animated.View
        style={[
          ringStyle,
          {
            position: 'absolute',
            width: 22,
            height: 22,
            borderRadius: 11,
            borderWidth: 2,
            borderColor: colors.border,
            backgroundColor: colors.fill + '40', // 25% opacity
          },
        ]}
      />
      <Animated.View
        style={[
          containerStyle,
          {
            width: 18,
            height: 18,
            borderRadius: 9,
            backgroundColor: colors.fill,
            borderWidth: 1.5,
            borderColor: colors.border,
            alignItems: 'center',
            justifyContent: 'center',
            shadowColor: '#000',
            shadowOpacity: 0.2,
            shadowRadius: 2,
            shadowOffset: { width: 0, height: 1 },
          },
        ]}
      >
        {displayContent && (
          <Text style={{ fontSize, fontWeight: '700', color: '#1a1410' }}>
            {displayContent}
          </Text>
        )}
      </Animated.View>
    </View>
  )
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
  showOrientControl = false,
  orientActive = false,
  onToggleOrient,
  orientClipUrl = null,
  orientAnnotation = null,
  orientIsPlaying = false,
  onToggleOrientPlayback,
  fretGuideCells = null,
  activeGuideIndex = null,
  chordCells = null,
  fretGuideFooterHint = null,
  pitchLadderSlot = null,
  pitchLadderDefaultExpanded,
  fretboardMode,
  onFretboardModeChange,
  voicingMode,
  onVoicingModeChange,
}: FretboardDiagramProps) {
  const [pitchLadderOpen, setPitchLadderOpen] = useState(
    () => pitchLadderDefaultExpanded ?? true,
  )
  const cell = selectedNote ? resolveFretCell(selectedNote) : null
  const flashMidi = selectedNote ? inferMidiFromNoteSelection(selectedNote) : null
  const showPitchLadderControl = pitchLadderSlot != null
  const [orientPanelOpen, setOrientPanelOpen] = useState(false)

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
        {showTuneControl || showOrientControl || showOverlayControls || showCopyShare || showPitchLadderControl || !!onFretboardModeChange ? (
          <View className="max-w-[76%] flex-row flex-wrap items-center justify-end gap-1.5">
            {/* Fretboard mode pills */}
            {onFretboardModeChange && ([
              { mode: 'auto' as const, label: 'Auto' },
              { mode: 'chords' as const, label: 'Chords' },
              { mode: 'solo' as const, label: 'Solo' },
              { mode: 'both' as const, label: 'Both' },
            ] as const).map(({ mode, label }) => (
              <Pressable
                key={mode}
                onPress={() => onFretboardModeChange(mode)}
                className={`rounded-full border px-2.5 py-1 ${
                  fretboardMode === mode ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/50'
                }`}
                accessibilityRole="button"
                accessibilityLabel={label}
                accessibilityState={{ selected: fretboardMode === mode }}
              >
                <Text className={`font-sans text-[11px] ${fretboardMode === mode ? 'text-wood-900' : 'text-muted-brown'}`}>{label}</Text>
              </Pressable>
            ))}
            {/* Voicing mode pills (only when chord-based mode active) */}
            {onVoicingModeChange && (fretboardMode === 'chords' || fretboardMode === 'both') && (
              <>
                <View className="mx-0.5 h-3 w-px bg-wood-600/35" />
                {([
                  { mode: 'compact' as const, label: 'Compact' },
                  { mode: 'full' as const, label: 'Full' },
                ] as const).map(({ mode, label }) => (
                  <Pressable
                    key={mode}
                    onPress={() => onVoicingModeChange(mode)}
                    className={`rounded-full border px-2.5 py-1 ${
                      voicingMode === mode ? 'border-success bg-success/20' : 'border-wood-600/45 bg-cream-dark/50'
                    }`}
                    accessibilityRole="button"
                    accessibilityLabel={label}
                    accessibilityState={{ selected: voicingMode === mode }}
                  >
                    <Text className={`font-sans text-[11px] ${voicingMode === mode ? 'text-wood-900' : 'text-muted-brown'}`}>{label}</Text>
                  </Pressable>
                ))}
                <View className="mx-0.5 h-3 w-px bg-wood-600/35" />
              </>
            )}
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
            {showOrientControl ? (
              <Pressable
                onPress={() => {
                  setOrientPanelOpen((o) => !o)
                  onToggleOrient?.()
                }}
                className={`rounded-full border px-3 py-1 ${orientPanelOpen ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/50'}`}
                accessibilityRole="button"
                accessibilityLabel={orientPanelOpen ? 'Hide technique hint' : 'Show technique hint'}
              >
                <Text className={`font-sans text-[11px] ${orientPanelOpen ? 'text-wood-900' : 'text-muted-brown'}`}>
                  {orientPanelOpen ? 'Hint' : 'Hint'}
                </Text>
              </Pressable>
            ) : null}
            {showPitchLadderControl ? (
              <Pressable
                onPress={() => setPitchLadderOpen((o) => !o)}
                className={`rounded-full border px-3 py-1 ${pitchLadderOpen ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/50'}`}
                accessibilityRole="button"
                accessibilityLabel="Show example pitch ladder"
                accessibilityState={{ selected: pitchLadderOpen }}
              >
                <Text className={`font-sans text-[11px] ${pitchLadderOpen ? 'text-wood-900' : 'text-muted-brown'}`}>
                  Example
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

      {orientPanelOpen && showOrientControl ? (
        <View className="mt-2 rounded-lg border border-wood-600/35 bg-ivory/35 px-2.5 py-2">
          <Text className="font-sans-semibold text-[11px] text-wood-900">Technique Hint</Text>
          {orientAnnotation ? (
            <Text className="mt-1 font-sans text-[11px] text-muted-brown">{orientAnnotation}</Text>
          ) : null}
          {orientClipUrl ? (
            <Pressable
              onPress={onToggleOrientPlayback}
              className="mt-2 rounded-md border border-wood-600/50 bg-cream-dark items-center justify-center py-2"
              accessibilityRole="button"
              accessibilityLabel={orientIsPlaying ? 'Pause technique clip' : 'Play technique clip'}
            >
              <Text className="font-sans-medium text-[11px] text-wood-900">
                {orientIsPlaying ? 'Pause' : 'Play Clip'}
              </Text>
            </Pressable>
          ) : (
            <Text className="mt-1 font-sans text-[11px] text-muted-brown">No hint clip available</Text>
          )}
        </View>
      ) : null}

      {pitchLadderOpen && pitchLadderSlot ? (
        <View className="mt-2">
          <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-muted-brown">
            Example · pitch ladder (Play)
          </Text>
          {pitchLadderSlot}
        </View>
      ) : null}

      <View className="mt-3 overflow-hidden rounded-lg border border-stone-400/55">
        <View className="flex-row border-b border-stone-400/55 bg-stone-100 py-1.5">
          <LinearGradient
            colors={['#ddc9a8', '#c4a574', '#a68456']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.nutHeaderCell}
          />
          {Array.from({ length: NUM_FRETS + 1 }).map((_, col) => (
            <View key={`h-${col}`} className="flex-1 items-center justify-center border-r border-stone-400/55 bg-[#fafaf9]">
              <Text className="font-mono text-[9px] text-stone-600">{col === 0 ? 'O' : col}</Text>
            </View>
          ))}
        </View>

        {Array.from({ length: 6 }).map((_, stringIdx) => {
          const thickness = stringLineThicknessPx(stringIdx)
          const webStringStyle: ViewStyle =
            Platform.OS === 'web'
              ? stringLineWebBackground(thickness)
              : {
                  width: '100%',
                  height: thickness,
                  borderRadius: thickness / 2,
                  backgroundColor: '#78716c',
                  shadowColor: '#000',
                  shadowOffset: { width: 0, height: 1 },
                  shadowOpacity: 0.18,
                  shadowRadius: 1.25,
                  elevation: 2,
                }

          return (
            <View
              key={`s-${stringIdx}`}
              className={`relative flex-row items-stretch ${stringIdx < 5 ? 'border-b border-stone-400/35' : ''}`}
            >
              <LinearGradient
                colors={['#ddc9a8', '#c4a574', '#a68456']}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={styles.nutStringCell}
              >
                <Text style={styles.openStringNote}>{OPEN_STRING_NOTE_LETTERS[stringIdx]}</Text>
              </LinearGradient>

              <View className="relative min-h-[36px] flex-1 flex-row bg-[#fafaf9]">
                <View
                  pointerEvents="none"
                  className="absolute inset-0 z-[3] justify-center px-0"
                  style={{ zIndex: 3 }}
                >
                  <View style={webStringStyle} />
                </View>

                {Array.from({ length: NUM_FRETS + 1 }).map((__, col) => {
                  const fret = col
                  const inlay = fretInlayKind(fret, stringIdx)
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
                  const guideInfo = guideVariantAtCell(fretGuideCells, stringIdx, fret)
                  const isActiveGuide =
                    activeGuideIndex != null &&
                    fretGuideCells != null &&
                    activeGuideIndex < fretGuideCells.length &&
                    fretGuideCells[activeGuideIndex]?.string === stringIdx + 1 &&
                    cellMatchesDiagramCol(fretGuideCells[activeGuideIndex]!.fret, fret)
                  // Check if this cell is part of a chord shape
                  const chordCell = chordCells?.find(
                    (c) => c.string === stringIdx + 1 && cellMatchesDiagramCol(c.fret, fret)
                  )
                  const isChordRoot = chordCell?.interval === 0
                  const inlaySizeClass =
                    inlay === 'doubleUpper' || inlay === 'doubleLower' ? 'h-1.5 w-1.5' : 'h-2 w-2'

                  return (
                    <Pressable
                      key={`c-${stringIdx}-${col}`}
                      onPress={() => onSelectNote?.({ string: stringIdx + 1, fret, midi })}
                      disabled={!onSelectNote}
                      className={`relative z-[4] flex-1 items-center justify-center border-r border-stone-400/55 py-1 ${
                        col === 0 ? 'border-l-0' : ''
                      }`}
                      style={{ zIndex: 4 }}
                      accessibilityRole={onSelectNote ? 'button' : undefined}
                      accessibilityLabel={onSelectNote ? `String ${stringIdx + 1}, fret ${fret}` : undefined}
                    >
                      {inlay ? (
                        <View
                          className="absolute inset-0 items-center justify-center"
                          pointerEvents="none"
                          style={{ zIndex: 2 }}
                        >
                          <View className={`rounded-full bg-stone-500 ${inlaySizeClass}`} />
                        </View>
                      ) : null}
                      {feedbackHere && lastCellResult ? (
                        <View
                          className={`absolute z-[15] h-5 w-5 rounded-full border-2 ${feedbackRing}`}
                          style={{ zIndex: 15 }}
                        />
                      ) : null}
                      {/* Scale highlight - subtle background (lowest priority) */}
                      {scaleOn ? (
                        <View
                          className="absolute z-[5] h-4 w-4 rounded-full border border-emerald-400/55 bg-emerald-500/15"
                          style={{ zIndex: 5 }}
                        />
                      ) : null}

                      {/* Chord cell highlight */}
                      {chordCell ? (
                        <View
                          className={`absolute z-[7] h-4 w-4 rounded-full border ${
                            isChordRoot
                              ? 'border-amber-accent bg-amber-accent/40'
                              : 'border-amber-light bg-amber-accent/20'
                          }`}
                          style={{ zIndex: 7 }}
                        />
                      ) : null}

                      {/* Guide marker with finger colors - combines with overlay label */}
                      {guideInfo ? (
                        <View
                          className="absolute z-[10] items-center justify-center"
                          style={{ zIndex: 10 }}
                        >
                          <GuideMarker
                            finger={guideInfo.finger}
                            isActive={isActiveGuide}
                            overlayLabel={overlayLabel}
                          />
                        </View>
                      ) : overlayLabel ? (
                        /* Standalone overlay label when no guide */
                        <Text
                          className="relative z-[8] font-mono text-[8px] text-stone-800"
                          style={{ zIndex: 8 }}
                        >
                          {overlayLabel}
                        </Text>
                      ) : null}

                      {/* Selected note - always on top but doesn't hide others */}
                      {selected ? (
                        <View
                          className="absolute inset-0 z-20 items-center justify-center"
                          style={{ zIndex: 20 }}
                        >
                          <SelectedMarker key={pulseKey} flashMidi={flashMidi} />
                        </View>
                      ) : null}
                    </Pressable>
                  )
                })}
              </View>
            </View>
          )
        })}
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

const styles = StyleSheet.create({
  nutHeaderCell: {
    width: NUT_COLUMN_WIDTH,
    minHeight: 28,
    borderRightWidth: 3,
    borderRightColor: '#6b5344',
  },
  nutStringCell: {
    width: NUT_COLUMN_WIDTH,
    minHeight: 36,
    borderRightWidth: 3,
    borderRightColor: '#6b5344',
    alignItems: 'center',
    justifyContent: 'center',
  },
  openStringNote: {
    color: '#FFFFFF',
    fontWeight: '600',
    fontSize: 15,
    textShadowColor: 'rgba(0,0,0,0.35)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
})

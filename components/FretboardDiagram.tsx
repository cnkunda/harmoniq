import { LinearGradient } from 'expo-linear-gradient'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Platform,
  Pressable,
  Text,
  View,
  type LayoutChangeEvent,
} from 'react-native'
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
import {
  Circle,
  Defs,
  G,
  Line,
  LinearGradient as SvgLinearGradient,
  Path,
  RadialGradient as SvgRadialGradient,
  Rect as SvgRect,
  Stop,
  Svg,
  Text as SvgText,
} from 'react-native-svg'

import { spring } from '@/src/constants/animations'
import colors from '@/src/constants/colors'
import {
  NUM_FRETS,
  OPEN_MIDI_BY_ROW,
  inferMidiFromNoteSelection,
  resolveFretCell,
} from '@/src/music/fretboardCell'
import { pitchClassLabelFromMidi } from '@/src/music/noteNames'
import type { FretboardTunerState } from '@/src/session/useFretboardTuner'
import type { FretboardOverlayMode } from '@/src/utils/fretboardShareState'
import { useMusicState } from '@/src/context/MusicContext'
import { chordToFretboardCells, formatChordDisplay, parseChordSymbol, noteToPitchClass } from '@/src/music/chordVoicing'

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
  scalePitchClasses?: readonly number[] | null
  onSelectNote?: (note: { string: number; fret: number; midi: number }) => void
  lastCellResult?: FretboardLastCellResult | null
  overlayMode?: FretboardOverlayMode
  degreeRootPitchClass?: number | null
  enableKeyboardInput?: boolean
  showOverlayControls?: boolean
  onOverlayModeChange?: (mode: FretboardOverlayMode) => void
  showCopyShare?: boolean
  onCopyShareLink?: () => void
  showTuneControl?: boolean
  tuneActive?: boolean
  tuneDisabled?: boolean
  tuneCalibrating?: boolean
  onToggleTune?: () => void
  onCalibrateTune?: () => void
  tunerState?: FretboardTunerState | null
  showOrientControl?: boolean
  orientActive?: boolean
  onToggleOrient?: () => void
  orientClipUrl?: string | null
  orientAnnotation?: string | null
  orientIsPlaying?: boolean
  onToggleOrientPlayback?: () => void
  fretGuideCells?: ReadonlyArray<{ string: number; fret: number; variant: 'primary' | 'secondary'; finger?: 1 | 2 | 3 | 4 }> | null
  activeGuideIndex?: number | null
  chordCells?: ReadonlyArray<{ string: number; fret: number; interval?: number }> | null
  fretGuideFooterHint?: string | null
  pitchLadderSlot?: ReactNode
  pitchLadderDefaultExpanded?: boolean
  fretboardMode?: 'auto' | 'chords' | 'solo' | 'both'
  onFretboardModeChange?: (mode: 'auto' | 'chords' | 'solo' | 'both') => void
  voicingMode?: 'full' | 'compact'
  onVoicingModeChange?: (mode: 'full' | 'compact') => void
}

const FINGER_COLORS: Record<number, { fill: string; border: string }> = {
  1: { fill: '#60A5FA', border: '#3B82F6' },
  2: { fill: '#34D399', border: '#10B981' },
  3: { fill: '#FBBF24', border: '#F59E0B' },
  4: { fill: '#F87171', border: '#EF4444' },
}

const NOTE_ACTIVE_RED = '#E53935'

const SCALE_DEGREE_LABELS: Record<number, string> = {
  0: '1', 1: 'b2', 2: '2', 3: 'b3', 4: '3', 5: '4',
  6: 'b5', 7: '5', 8: '#5', 9: '6', 10: 'b7', 11: '7',
}

const KEYBOARD_ROWS = ['1234567890-=', 'qwertyuiop[]', "asdfghjkl;'", 'zxcvbnm,./'] as const
const SINGLE_INLAY_FRETS = new Set([3, 5, 7, 9])

// SVG layout constants
const SVG_W = 900
const SVG_H = 260
const MARGIN_L = 44
const MARGIN_R = 12
const BOARD_T = 36
const BOARD_B = 234
const BOARD_H = BOARD_B - BOARD_T
const NUT_W = 8
const FRET_START_X = MARGIN_L + NUT_W
const COL_W = (SVG_W - MARGIN_R - FRET_START_X) / 12

function stringY(i: number): number {
  return BOARD_T + BOARD_H * (i + 0.5) / 6
}

function fretCenterX(f: number): number {
  if (f === 0) return MARGIN_L + NUT_W / 2
  return FRET_START_X + COL_W * (f - 0.5)
}

function fretWireX(f: number): number {
  return FRET_START_X + COL_W * f
}

function fretInlayKind(fret: number, stringIdx: number): 'single' | 'doubleUpper' | 'doubleLower' | null {
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

function flashPeakColorForMidi(midi: number | null): string {
  if (midi == null || !Number.isFinite(midi)) return colors.cream
  const pc = ((Math.round(midi) % 12) + 12) % 12
  const hue = 26 + pc * 2.2
  return `hsl(${hue}, 76%, 76%)`
}

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

function cellMatchesDiagramCol(cellFret: number, col: number): boolean {
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

const OPEN_STRING_NOTE_LETTERS = OPEN_MIDI_BY_ROW.map((midi) => pitchClassLabelFromMidi(midi))

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
    borderColor: interpolateColor(colorPulse.value, [0, 1], [colors.amber.light, colors.ivory]),
  }))

  const ringStyle = useAnimatedStyle(() => ({
    opacity: interpolate(colorPulse.value, [0, 0.15, 1], [0, 0.55, 0.9]),
    transform: [{ scale: interpolate(colorPulse.value, [0, 1], [0.85, 1.75]) }],
  }))

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
            shadowColor: colors.wood[900],
            shadowOpacity: 0.22,
            shadowRadius: 3,
            shadowOffset: { width: 0, height: 1 },
          },
        ]}
      />
    </View>
  )
}

function GuideMarker({
  finger,
  isActive,
  overlayLabel,
}: {
  finger?: 1 | 2 | 3 | 4
  isActive?: boolean
  overlayLabel?: string | null | undefined
}) {
  const fc = finger ? FINGER_COLORS[finger] : { fill: colors.amber.accent, border: colors.amber.accent }
  const scaleVal = useSharedValue(1)
  const pulseAnim = useSharedValue(0)

  useEffect(() => {
    scaleVal.value = 1
    pulseAnim.value = 0
    if (isActive) {
      scaleVal.value = withSequence(withSpring(1.25, spring.snappy), withSpring(1.1, spring.gentle))
      pulseAnim.value = withSequence(
        withTiming(1, { duration: 150, easing: Easing.out(Easing.quad) }),
        withTiming(0, { duration: 300, easing: Easing.in(Easing.quad) }),
      )
    }
  }, [isActive, scaleVal, pulseAnim])

  const containerStyle = useAnimatedStyle(() => ({ transform: [{ scale: scaleVal.value }] }))
  const ringStyle = useAnimatedStyle(() => ({
    opacity: isActive ? interpolate(pulseAnim.value, [0, 0.5, 1], [0.6, 0.9, 0.6]) : 0.4,
    transform: [{ scale: isActive ? interpolate(pulseAnim.value, [0, 1], [1, 1.4]) : 1 }],
  }))

  const displayContent = overlayLabel ?? (finger ? finger.toString() : null)
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
            borderColor: fc.border,
            backgroundColor: fc.fill + '40',
          },
        ]}
      />
      <Animated.View
        style={[
          containerStyle,
          {
            width: 18, height: 18, borderRadius: 9,
            backgroundColor: fc.fill, borderWidth: 1.5, borderColor: fc.border,
            alignItems: 'center', justifyContent: 'center',
            shadowColor: colors.wood[900], shadowOpacity: 0.2, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
          },
        ]}
      >
        {displayContent && (
          <Text style={{ fontSize, fontWeight: '700', color: colors.wood[900] }}>
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
  chordCells: chordCellsProp = null,
  fretGuideFooterHint = null,
  pitchLadderSlot = null,
  pitchLadderDefaultExpanded,
  fretboardMode,
  onFretboardModeChange,
  voicingMode,
  onVoicingModeChange,
}: FretboardDiagramProps) {
  const [pitchLadderOpen, setPitchLadderOpen] = useState(() => pitchLadderDefaultExpanded ?? true)
  const [orientPanelOpen, setOrientPanelOpen] = useState(false)
  const [svgSize, setSvgSize] = useState({ w: 0, h: 0 })

  // MusicContext integration (optional – graceful fallback if no provider in tree)
  let musicState: { currentChord: string | null; activeNotes: Array<{ string: number; fret: number; midi?: number }> } | null = null
  try {
    musicState = useMusicState()
  } catch {
    // No MusicProvider in tree; that's fine
  }

  const cell = selectedNote ? resolveFretCell(selectedNote) : null
  const flashMidi = selectedNote ? inferMidiFromNoteSelection(selectedNote) : null
  const showPitchLadderControl = pitchLadderSlot != null

  // Derive chord cells: prefer prop, then compute from MusicContext
  const chordCells = useMemo(() => {
    if (chordCellsProp && chordCellsProp.length > 0) return chordCellsProp
    if (musicState?.currentChord && musicState.currentChord !== 'N') {
      const cells = chordToFretboardCells(musicState.currentChord, voicingMode ?? 'compact', 'low')
      return cells.map(c => ({ string: c.string, fret: c.fret, interval: c.interval }))
    }
    return []
  }, [chordCellsProp, musicState?.currentChord, voicingMode])

  // Chord name from MusicContext or fallback
  const chordName = useMemo(() => {
    if (musicState?.currentChord && musicState.currentChord !== 'N') {
      return formatChordDisplay(musicState.currentChord)
    }
    return null
  }, [musicState?.currentChord])

  const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

  const CHORD_FULL_NAMES: Record<string, string> = {
    maj: 'Major', min: 'Minor', dim: 'Diminished', aug: 'Augmented',
    '7': 'Dominant 7th', maj7: 'Major 7th', min7: 'Minor 7th',
    '7sus4': '7th Sus 4', sus4: 'Sus 4', sus2: 'Sus 2',
    '6': 'Major 6th', min6: 'Minor 6th',
    '9': 'Dominant 9th', maj9: 'Major 9th', min9: 'Minor 9th',
  }

  const EXTENSIONS: Record<string, string[]> = {
    maj: ['7', 'maj7', '6', '9', 'maj9'],
    min: ['m7', 'm9', 'm11', 'm13', 'mM7'],
    dim: ['dim7', 'm7b5'],
    aug: ['aug7', 'maj7#5'],
    '7': ['9', '13', '7sus4', '7#9', '7b9'],
    maj7: ['9', '13', 'maj9', '#11'],
    min7: ['m9', 'm11', 'm13'],
    '7sus4': ['9sus4', '13sus4'],
    sus4: ['7sus4', '9sus4'],
    sus2: ['7sus2', '9sus2'],
    '6': ['7', 'maj7', '9'],
    min6: ['m7', 'm9'],
    '9': ['13', '7#9', '7b9'],
    maj9: ['13', '#11'],
    min9: ['11', '13'],
  }

  const chordNotes = useMemo(() => {
    if (!musicState?.currentChord || musicState.currentChord === 'N') return []
    const parsed = parseChordSymbol(musicState.currentChord)
    if (!parsed) return []
    const rootPc = noteToPitchClass(parsed.root)
    const intervals = [...new Set(chordCells.map(c => c.interval))]
    return intervals
      .sort((a, b) => a - b)
      .filter(iv => iv >= 0 && iv <= 12)
      .map(iv => NOTE_NAMES[(rootPc + iv) % 12])
  }, [musicState?.currentChord, chordCells])

  const chordFullName = useMemo(() => {
    if (!musicState?.currentChord || musicState.currentChord === 'N') return null
    const parsed = parseChordSymbol(musicState.currentChord)
    if (!parsed) return null
    return CHORD_FULL_NAMES[parsed.quality] ?? parsed.quality
  }, [musicState?.currentChord])

  const chordExtensions = useMemo(() => {
    if (!musicState?.currentChord || musicState.currentChord === 'N') return []
    const parsed = parseChordSymbol(musicState.currentChord)
    if (!parsed) return []
    const exts = EXTENSIONS[parsed.quality]
    if (!exts) return []
    return exts.map(ext => `${parsed.root}${ext}`)
  }, [musicState?.currentChord])

  // Active notes from MusicContext or fallback to selectedNote
  const activeNotes = useMemo(() => {
    if (musicState?.activeNotes && musicState.activeNotes.length > 0) {
      return musicState.activeNotes
    }
    return []
  }, [musicState?.activeNotes])

  // Display mode filtering for SVG rendering
  const showChords = useMemo(() => {
    if (!fretboardMode || fretboardMode === 'auto' || fretboardMode === 'both' || fretboardMode === 'chords') return true
    return false
  }, [fretboardMode])

  const showSoloNotes = useMemo(() => {
    if (!fretboardMode || fretboardMode === 'auto' || fretboardMode === 'both' || fretboardMode === 'solo') return true
    return false
  }, [fretboardMode])

  const onSvgLayout = useCallback((e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width
    setSvgSize({ w, h: w * SVG_H / SVG_W })
  }, [])

  useEffect(() => {
    if (!onSelectNote || !enableKeyboardInput || Platform.OS !== 'web') return
    const handler = (evt: KeyboardEvent) => {
      const target = evt.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
      if (evt.ctrlKey || evt.metaKey || evt.altKey) return
      const key = evt.key.toLowerCase()
      let rowIndex = -1
      let fret = -1
      for (let i = 0; i < KEYBOARD_ROWS.length; i += 1) {
        const idx = KEYBOARD_ROWS[i].indexOf(key)
        if (idx >= 0) { rowIndex = i; fret = idx; break }
      }
      if (rowIndex < 0 || fret < 0 || fret > NUM_FRETS) return
      let stringIdx = 5 - rowIndex
      if (evt.shiftKey && rowIndex <= 1) {
        stringIdx = rowIndex === 0 ? 1 : 0
      }
      if (stringIdx < 0 || stringIdx > 5) return
      evt.preventDefault()
      onSelectNote({ string: stringIdx + 1, fret, midi: OPEN_MIDI_BY_ROW[stringIdx]! + fret })
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [enableKeyboardInput, onSelectNote])

  const handleCellPress = useCallback((stringIdx: number, fret: number) => {
    if (!onSelectNote) return
    onSelectNote({ string: stringIdx + 1, fret, midi: OPEN_MIDI_BY_ROW[stringIdx]! + fret })
  }, [onSelectNote])

  // Pre-compute SVG cell data for tap targets
  const svgCells = useMemo(() => {
    const cells: Array<{
      stringIdx: number
      fret: number
      sx: number
      sy: number
      ex: number
      ey: number
    }> = []
    for (let si = 0; si < 6; si++) {
      for (let f = 0; f <= NUM_FRETS; f++) {
        let sx: number, ex: number
        if (f === 0) {
          sx = MARGIN_L
          ex = FRET_START_X + COL_W
        } else {
          sx = FRET_START_X + COL_W * (f - 1)
          ex = FRET_START_X + COL_W * f
        }
        const sy = stringY(si) - BOARD_H / 12
        const ey = stringY(si) + BOARD_H / 12
        cells.push({ stringIdx: si, fret: f, sx, sy, ex, ey })
      }
    }
    return cells
  }, [])

  const feedbackRingColor = lastCellResult
    ? lastCellResult.result === 'hit'
      ? colors.success
      : lastCellResult.result === 'close'
        ? colors.amber.accent
        : colors.danger
    : null

  const feedbackX = lastCellResult
    ? fretCenterX(lastCellResult.fret)
    : 0
  const feedbackY = lastCellResult
    ? stringY(lastCellResult.row)
    : 0

  return (
    <View className="mt-3 rounded-xl border border-wood-600/45 bg-cream-dark/45 p-3">
      <View className="flex-row items-start justify-between gap-5">
        <View className="gap-1" style={{ minWidth: 130 }}>
          <Text className="font-sans-medium text-[10px] uppercase tracking-[0.14em] text-amber-accent">Position map</Text>
          <View className="flex-row items-baseline gap-2">
            <Text className="font-sans text-base font-semibold text-wood-900">{keyLabel}</Text>
            {capoText ? (
              <View className="rounded-full border border-amber-accent/25 bg-amber-accent/10 px-[7px] py-0.5">
                <Text className="text-[10px] font-medium text-amber-accent/70">{capoText}</Text>
              </View>
            ) : null}
          </View>
        </View>
        <View className="flex-1 flex-row flex-wrap items-center justify-end gap-1.5">
          {onFretboardModeChange && (
            <View className="flex-row rounded-full border border-wood-600/45 bg-cream-dark/30 p-0.5 gap-[2px]">
              {([
                { mode: 'auto' as const, label: 'Auto' },
                { mode: 'chords' as const, label: 'Chord' },
                { mode: 'solo' as const, label: 'Solo' },
                { mode: 'both' as const, label: 'Both' },
              ] as const).map(({ mode, label }) => (
                <Pressable
                  key={mode}
                  onPress={() => onFretboardModeChange(mode)}
                  className={`rounded-full px-4 py-1.5 ${
                    fretboardMode === mode ? 'bg-amber-accent/20' : ''
                  }`}
                  accessibilityRole="button"
                  accessibilityLabel={label}
                  accessibilityState={{ selected: fretboardMode === mode }}
                >
                  <Text className={`font-sans text-xs ${
                    fretboardMode === mode ? 'text-amber-accent font-medium' : 'text-muted-brown'
                  }`}>{label}</Text>
                </Pressable>
              ))}
            </View>
          )}

          {tuneActive && onCalibrateTune ? (
            <Pressable
              onPress={onCalibrateTune}
              className="rounded-full border border-wood-600/45 bg-cream-dark/50 px-3 py-1.5"
              accessibilityRole="button"
              accessibilityLabel="Calibrate tuner noise floor"
            >
              <Text className="font-mono text-[10px] text-wood-900">{tuneCalibrating ? 'Cal…' : 'Cal'}</Text>
            </Pressable>
          ) : null}

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
                  className={`rounded-full border px-3 py-1.5 ${
                    voicingMode === mode ? 'border-success bg-success/20' : 'border-wood-600/45 bg-cream-dark/50'
                  }`}
                  accessibilityRole="button"
                  accessibilityLabel={label}
                  accessibilityState={{ selected: voicingMode === mode }}
                >
                  <Text className={`font-sans text-[11px] ${voicingMode === mode ? 'text-wood-900' : 'text-muted-brown'}`}>{label}</Text>
                </Pressable>
              ))}
            </>
          )}

          {showOverlayControls && (
            <>
              {!!onVoicingModeChange && (fretboardMode === 'chords' || fretboardMode === 'both') ? (
                <View className="mx-0.5 h-3 w-px bg-wood-600/35" />
              ) : null}
              {([
                { mode: 'off' as const, label: 'Overlay' },
                { mode: 'note_names' as const, label: 'Labels' },
                { mode: 'scale_degrees' as const, label: 'Degrees' },
              ] as const).map(({ mode, label }) => (
                <Pressable
                  key={mode}
                  onPress={() => onOverlayModeChange?.(mode)}
                  disabled={!onOverlayModeChange}
                  className={`rounded-full border px-3 py-1.5 ${
                    overlayMode === mode ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/50'
                  } ${onOverlayModeChange ? '' : 'opacity-50'}`}
                  accessibilityRole="button"
                  accessibilityLabel={label}
                  accessibilityState={{ selected: overlayMode === mode }}
                >
                  <Text className={`font-sans text-[11px] ${overlayMode === mode ? 'text-wood-900' : 'text-muted-brown'}`}>{label}</Text>
                </Pressable>
              ))}
            </>
          )}

          {showPitchLadderControl ? (
            <Pressable
              onPress={() => setPitchLadderOpen((o) => !o)}
              className={`rounded-full border px-3 py-1.5 ${pitchLadderOpen ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/50'}`}
              accessibilityRole="button"
              accessibilityLabel="Show example pitch ladder"
              accessibilityState={{ selected: pitchLadderOpen }}
            >
              <Text className={`font-sans text-[11px] ${pitchLadderOpen ? 'text-wood-900' : 'text-muted-brown'}`}>Example</Text>
            </Pressable>
          ) : null}

          {(showTuneControl || showOrientControl || showCopyShare) &&
           (!!onFretboardModeChange || !!onVoicingModeChange || showOverlayControls || showPitchLadderControl || tuneActive) ? (
            <View className="mx-0.5 h-[18px] w-px bg-wood-600/25" />
          ) : null}

          {showTuneControl ? (
            <Pressable
              onPress={onToggleTune}
              disabled={tuneDisabled}
              className={`h-[34px] w-[34px] items-center justify-center rounded-lg border ${tuneActive ? 'border-success bg-success/25' : 'border-wood-600/45'} ${tuneDisabled ? 'opacity-45' : ''}`}
              accessibilityRole="button"
              accessibilityLabel={tuneActive ? 'Disable fretboard tuner' : 'Enable fretboard tuner'}
            >
              <Svg viewBox="0 0 24 24" width={16} height={16}>
                <Circle cx={12} cy={12} r={3} stroke={colors.muted.brown} strokeWidth={1.5} fill="none" />
                <Path
                  d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83"
                  stroke={colors.muted.brown} strokeWidth={1.5} strokeLinecap="round" fill="none"
                />
              </Svg>
            </Pressable>
          ) : null}

          {showOrientControl ? (
            <Pressable
              onPress={() => { setOrientPanelOpen((o) => !o); onToggleOrient?.() }}
              className={`h-[34px] w-[34px] items-center justify-center rounded-lg border ${orientPanelOpen ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45'}`}
              accessibilityRole="button"
              accessibilityLabel={orientPanelOpen ? 'Hide technique hint' : 'Show technique hint'}
            >
              <Svg viewBox="0 0 24 24" width={16} height={16}>
                <Circle cx={12} cy={12} r={10} stroke={colors.muted.brown} strokeWidth={1.5} fill="none" />
                <Path d="M12 16v-4m0-4h.01" stroke={colors.muted.brown} strokeWidth={1.5} strokeLinecap="round" fill="none" />
              </Svg>
            </Pressable>
          ) : null}

          {showCopyShare ? (
            <Pressable
              onPress={onCopyShareLink}
              disabled={!onCopyShareLink}
              className={`h-[34px] w-[34px] items-center justify-center rounded-lg border border-wood-600/45 ${onCopyShareLink ? '' : 'opacity-50'}`}
              accessibilityRole="button"
              accessibilityLabel="Copy share link"
            >
              <Svg viewBox="0 0 24 24" width={16} height={16}>
                <Path
                  d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8m-4-6-4-4-4 4m4-4v13"
                  stroke={colors.muted.brown} strokeWidth={1.5} strokeLinecap="round"
                  strokeLinejoin="round" fill="none"
                />
              </Svg>
            </Pressable>
          ) : null}
        </View>
      </View>
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
          <Text className="font-sans-medium text-[11px] text-wood-900">Technique Hint</Text>
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

      {/* SVG Fretboard */}
      <View
        onLayout={onSvgLayout}
        className="mt-3 overflow-hidden rounded-lg"
        style={{ width: '100%', height: svgSize.h || 200 }}
      >
        {svgSize.w > 0 && (
          <Svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} width={svgSize.w} height={svgSize.h}>
            <Defs>
              <SvgLinearGradient id="woodBg" x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0%" stopColor={colors.wood[800]} />
                <Stop offset="100%" stopColor={colors.wood[900]} />
              </SvgLinearGradient>
              <SvgRadialGradient id="noteGlow" cx="50%" cy="50%" r="50%">
                <Stop offset="0%" stopColor={NOTE_ACTIVE_RED} stopOpacity="0.35" />
                <Stop offset="100%" stopColor={NOTE_ACTIVE_RED} stopOpacity="0" />
              </SvgRadialGradient>
              <SvgRadialGradient id="chordRootGlow" cx="50%" cy="50%" r="50%">
                <Stop offset="0%" stopColor="#D4A574" stopOpacity="0.45" />
                <Stop offset="100%" stopColor="#D4A574" stopOpacity="0" />
              </SvgRadialGradient>
            </Defs>

            {/* Wood background */}
            <SvgRect x="0" y="0" width={SVG_W} height={SVG_H} fill="url(#woodBg)" rx="6" />

            {/* Fret numbers (O for nut, 1-12 for frets) */}
            <SvgText
              x={fretCenterX(0)}
              y={26}
              textAnchor="middle"
              fill={colors.muted.brown}
              fontSize={9}
              fontFamily="JetBrainsMono-Regular"
            >
              O
            </SvgText>
            {Array.from({ length: 12 }).map((_, i) => (
              <SvgText
                key={`fn-${i}`}
                x={fretCenterX(i + 1)}
                y={26}
                textAnchor="middle"
                fill={colors.muted.brown}
                fontSize={9}
                fontFamily="JetBrainsMono-Regular"
              >
                {i + 1}
              </SvgText>
            ))}

            {/* Open string labels */}
            {OPEN_STRING_NOTE_LETTERS.map((label, i) => (
              <SvgText
                key={`os-${i}`}
                x={MARGIN_L - 6}
                y={stringY(i) + 4}
                textAnchor="end"
                fill={colors.amber.accent}
                fontSize={11}
                fontWeight="600"
              >
                {label}
              </SvgText>
            ))}

            {/* Nut (ivory) */}
            <SvgRect
              x={MARGIN_L}
              y={BOARD_T}
              width={NUT_W}
              height={BOARD_H}
              fill="#F5F0E8"
              rx={1}
              stroke="#D4A574"
              strokeWidth={0.5}
            />

            {/* Fret wires (silver vertical lines) */}
            {Array.from({ length: 12 }).map((_, i) => (
              <Line
                key={`fw-${i}`}
                x1={fretWireX(i + 1)}
                y1={BOARD_T - 4}
                x2={fretWireX(i + 1)}
                y2={BOARD_B + 4}
                stroke={colors.muted.brown}
                strokeWidth={1.2}
                opacity={0.7}
              />
            ))}

            {/* Fret inlays */}
            {Array.from({ length: 6 }).map((_, si) =>
              Array.from({ length: NUM_FRETS + 1 }).map((_, col) => {
                const inlay = fretInlayKind(col, si)
                if (!inlay) return null
                const cx = fretCenterX(col)
                const cy = stringY(si)
                if (inlay === 'single') {
                  return (
                    <Circle
                      key={`inl-${si}-${col}`}
                      cx={cx}
                      cy={cy}
                      r={4.5}
                      fill="#8B7D6B"
                      opacity={0.55}
                    />
                  )
                }
                if (inlay === 'doubleUpper') {
                  return (
                    <Circle
                      key={`inl-${si}-${col}`}
                      cx={cx}
                      cy={cy - 8}
                      r={3.5}
                      fill="#8B7D6B"
                      opacity={0.55}
                    />
                  )
                }
                if (inlay === 'doubleLower') {
                  return (
                    <Circle
                      key={`inl-${si}-${col}`}
                      cx={cx}
                      cy={cy + 8}
                      r={3.5}
                      fill="#8B7D6B"
                      opacity={0.55}
                    />
                  )
                }
                return null
              }),
            )}

            {/* Strings (horizontal lines, varying thickness) */}
            {Array.from({ length: 6 }).map((_, si) => (
              <Line
                key={`str-${si}`}
                x1={MARGIN_L}
                y1={stringY(si)}
                x2={SVG_W - MARGIN_R}
                y2={stringY(si)}
                stroke={colors.muted.brown}
                strokeWidth={stringLineThicknessPx(si) * 2.2}
                opacity={0.75}
              />
            ))}

            {/* Scale highlights */}
            {Array.from({ length: 6 }).map((_, si) =>
              Array.from({ length: NUM_FRETS + 1 }).map((_, col) => {
                if (!scaleHighlightActive(scalePitchClasses, si, col)) return null
                const midi = OPEN_MIDI_BY_ROW[si]! + col
                const isActiveNote = activeNotes.some(n => n.midi === midi)
                if (isActiveNote) return null // don't double-highlight
                return (
                  <Circle
                    key={`sc-${si}-${col}`}
                    cx={fretCenterX(col === 0 ? 0 : col)}
                    cy={stringY(si)}
                    r={7}
                    fill={colors.success}
                    opacity={0.15}
                    stroke={colors.success}
                    strokeWidth={0.8}
                    strokeOpacity={0.4}
                  />
                )
              }),
            )}

            {/* Chord voicing circles */}
            {showChords && chordCells?.map((cc, idx) => {
              const si = cc.string - 1
              const col = cc.fret
              if (si < 0 || si > 5) return null
              const isRoot = cc.interval === 0
              // Check if this note is already an active note
              const isActiveChordNote = activeNotes.some(n => n.string === cc.string && n.fret === cc.fret)
              if (isActiveChordNote) return null // active notes render separately
              return (
                <Circle
                  key={`ch-${idx}`}
                  cx={fretCenterX(col)}
                  cy={stringY(si)}
                  r={isRoot ? 8 : 6}
                  fill={isRoot ? colors.amber.accent : colors.amber.light}
                  opacity={isRoot ? 0.85 : 0.55}
                  stroke={isRoot ? colors.amber.accent : colors.amber.light}
                  strokeWidth={0.5}
                />
              )
            })}

            {/* Active notes (red glow + text) */}
            {showSoloNotes && activeNotes.map((note, idx) => {
              const si = note.string - 1
              const col = note.fret
              if (si < 0 || si > 5) return null
              const cx = fretCenterX(col)
              const cy = stringY(si)
              const pitchLabel = note.midi ? pitchClassLabelFromMidi(note.midi) : ''
              return (
                <G key={`an-${idx}`}>
                  <Circle cx={cx} cy={cy} r={14} fill="url(#noteGlow)" />
                  <Circle cx={cx} cy={cy} r={7} fill={NOTE_ACTIVE_RED} />
                  {pitchLabel ? (
                    <SvgText
                      x={cx}
                      y={cy + 3.5}
                      textAnchor="middle"
                      fill={colors.white}
                      fontSize={8}
                      fontWeight="700"
                      stroke={colors.wood[900]}
                      strokeWidth={2.5}
                    >
                      {pitchLabel}
                    </SvgText>
                  ) : null}
                </G>
              )
            })}

            {/* Feedback ring (Play tab hit/miss) */}
            {lastCellResult && (
              <Circle
                cx={feedbackX}
                cy={feedbackY}
                r={10}
                fill="none"
                stroke={feedbackRingColor!}
                strokeWidth={2.5}
                opacity={0.85}
              />
            )}

            {/* Guide markers */}
            {fretGuideCells?.map((gc, idx) => {
              const si = gc.string - 1
              const col = gc.fret
              if (si < 0 || si > 5) return null
              const isActive = activeGuideIndex === idx
              const midi = OPEN_MIDI_BY_ROW[si]! + col
              const ol = overlayLabelForCell(overlayMode, midi, degreeRootPitchClass)
              const fc = gc.finger ? FINGER_COLORS[gc.finger] : { fill: colors.amber.accent, border: colors.amber.accent }
              const ringR = isActive ? 11 : 9
              return (
                <G key={`gm-${idx}`}>
                  <Circle
                    cx={fretCenterX(col)}
                    cy={stringY(si)}
                    r={ringR}
                    fill={fc.fill + '30'}
                    stroke={fc.border}
                    strokeWidth={1.5}
                    opacity={isActive ? 0.9 : 0.5}
                  />
                  <SvgText
                    x={fretCenterX(col)}
                    y={stringY(si) + 3.5}
                    textAnchor="middle"
                    fill={colors.wood[900]}
                    fontSize={ol && ol.length > 1 ? 8 : 10}
                    fontWeight="700"
                  >
                    {ol ?? (gc.finger ? gc.finger.toString() : '')}
                  </SvgText>
                </G>
              )
            })}

            {/* Overlay labels */}
            {overlayMode !== 'off' && !fretGuideCells && (
              Array.from({ length: 6 }).map((_, si) =>
                Array.from({ length: NUM_FRETS + 1 }).map((_, col) => {
                  const midi = OPEN_MIDI_BY_ROW[si]! + col
                  const label = overlayLabelForCell(overlayMode, midi, degreeRootPitchClass)
                  if (!label) return null
                  return (
                    <SvgText
                      key={`ol-${si}-${col}`}
                      x={fretCenterX(col)}
                      y={stringY(si) + 3}
                      textAnchor="middle"
                      fill="#8B7D6B"
                      fontSize={7}
                      fontFamily="JetBrainsMono-Regular"
                      opacity={0.8}
                    >
                      {label}
                    </SvgText>
                  )
                }),
              )
            )}

            {/* Tap targets (transparent pressable rects) */}
            {svgCells.map(({ stringIdx, fret, sx, sy, ex, ey }) => (
              <SvgRect
                key={`tap-${stringIdx}-${fret}`}
                x={sx}
                y={sy}
                width={ex - sx}
                height={ey - sy}
                fill="transparent"
                onPress={() => handleCellPress(stringIdx, fret)}
              />
            ))}
          </Svg>
        )}

        {/* Animated overlays positioned over SVG (selected note pulse) */}
        {cell && svgSize.w > 0 && (
          <View
            style={{
              position: 'absolute',
              left: (fretCenterX(cell.fret) / SVG_W) * svgSize.w - 14,
              top: (stringY(cell.row) / SVG_H) * svgSize.h - 14,
            }}
            pointerEvents="none"
          >
            <SelectedMarker key={pulseKey} flashMidi={flashMidi} />
          </View>
        )}

        {/* Guide marker animated overlays */}
        {fretGuideCells?.map((gc, idx) => {
          if (activeGuideIndex !== idx) return null
          const si = gc.string - 1
          const col = gc.fret
          if (si < 0 || si > 5) return null
          if (!svgSize.w) return null
          const midi = OPEN_MIDI_BY_ROW[si]! + col
          const ol = overlayLabelForCell(overlayMode, midi, degreeRootPitchClass)
          return (
            <View
              key={`gm-anim-${idx}`}
              style={{
                position: 'absolute',
                left: (fretCenterX(col) / SVG_W) * svgSize.w - 14,
                top: (stringY(si) / SVG_H) * svgSize.h - 14,
              }}
              pointerEvents="none"
            >
              <GuideMarker finger={gc.finger} isActive overlayLabel={ol} />
            </View>
          )
        })}
      </View>

      {chordName && chordNotes.length > 0 ? (
        <View className="mt-2 border-t border-wood-600/20 pt-3">
          <View className="flex-row items-center">
            <View className="flex-row items-baseline gap-3 pr-4 border-r border-wood-600/20">
              <Text className="font-serif text-3xl tracking-tight text-amber-accent">
                {chordName}
              </Text>
              {chordFullName ? (
                <Text className="text-[11px] uppercase tracking-widest text-amber-accent/60 font-medium">
                  {chordFullName}
                </Text>
              ) : null}
            </View>
            <View className="px-4 border-r border-wood-600/20">
              <Text className="text-[9px] uppercase tracking-wider text-amber-accent/50 mb-0.5">
                Notes
              </Text>
              <View className="flex-row items-center gap-1.5">
                {chordNotes.map((note, idx) => (
                  <View key={note} className="flex-row items-center gap-1.5">
                    {idx > 0 && (
                      <View className="h-1 w-1 rounded-full bg-amber-accent/30" />
                    )}
                    <Text className="text-sm font-medium text-amber-accent">{note}</Text>
                  </View>
                ))}
              </View>
            </View>
            {chordExtensions.length > 0 ? (
              <View className="flex-1 pl-4">
                <Text className="text-[9px] uppercase tracking-wider text-amber-accent/50 mb-1">
                  Extended harmony
                </Text>
                <View className="flex-row flex-wrap gap-1.5">
                  {chordExtensions.map((ext) => (
                    <View
                      key={ext}
                      className="rounded-full border border-wood-600/30 px-2 py-0.5"
                    >
                      <Text className="text-[10px] font-medium text-amber-accent/70">
                        {ext}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : null}
            <Text className="ml-auto font-mono text-[10px] text-muted-brown">Tap a note to identify position</Text>
          </View>
        </View>
      ) : null}

      {cell ? (
        <Text className="mt-2 font-mono text-[10px] text-muted-brown">
          Selected · string {cell.row + 1} (tab) · fret {cell.fret} · pulse #{pulseKey}
        </Text>
      ) : !fretGuideFooterHint && !(chordName && chordNotes.length > 0) ? (
        <Text className="mt-2 font-mono text-[10px] text-muted-brown">Tap a note to identify position</Text>
      ) : fretGuideFooterHint ? (
        <Text className="mt-2 font-mono text-[10px] text-muted-brown">{fretGuideFooterHint}</Text>
      ) : null}
    </View>
  )
}

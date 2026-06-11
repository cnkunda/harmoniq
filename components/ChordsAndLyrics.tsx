import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LayoutChangeEvent, ScrollView, Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated'
import { Guitar, Lock, Minus, Plus, Unlock } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ChordDiagram } from './ChordDiagram'
import { SectionNavigator } from './SectionNavigator'

import colors from '@/src/constants/colors'
import { spring, timing } from '@/src/constants/animations'

export interface BarData {
  chord: string
  chord2?: string
  text?: string
  /** Commit 116: Roman numeral functional label (e.g., 'I', 'ii7', 'V7') */
  roman?: string
}

interface ChordsAndLyricsProps {
  bars: BarData[]
  currentBar?: number
  bpm?: number
  /** timeSignature[0] is numerator (beats per bar). Default [4,4] */
  timeSignature?: [number, number]
  onBarPress?: (barIndex: number) => void
  onBarLongPress?: (barIndex: number) => void
  /** Commit 110: Tap a chord symbol to open correction UI. */
  onChordTap?: (barIndex: number, chord: string) => void
  /** Number of bars per line in the chord sheet (default: 4) */
  barsPerLine?: number
  /** Optional section label to display above the chord sheet */
  label?: string
  /** Commit 119: label confidence (0-1). When <0.6, shown as uncertain. */
  labelConfidence?: number | null
  /** Layout mode: 'grid' keeps barsPerLine grouping, 'flow' uses flex-wrap */
  layoutMode?: 'grid' | 'flow'
}

const CHROMATIC = [
  'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B',
]

function transposeChord(chord: string, semitones: number): string {
  if (!chord || semitones === 0) return chord
  const match = chord.match(/^([A-G][#b]?)(.*)$/)
  if (!match) return chord
  const [, root, suffix] = match
  const flatToSharp: Record<string, string> = {
    Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#',
  }
  const normalized = flatToSharp[root] || root
  const idx = CHROMATIC.indexOf(normalized)
  if (idx === -1) return chord
  const newIdx = (idx + semitones + 12 * 4) % 12
  return CHROMATIC[newIdx] + suffix
}

const ACTIVE_BAR_ANIM_DURATION = 250

export function ChordsAndLyrics({
  bars,
  currentBar,
  bpm = 92,
  timeSignature = [4, 4],
  onBarPress,
  onBarLongPress,
  onChordTap,
  barsPerLine = 4,
  label,
  labelConfidence,
  layoutMode = 'flow',
}: ChordsAndLyricsProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [internalBar, setInternalBar] = useState(0)
  const [transpose, setTranspose] = useState(0)
  const [showShapes, setShowShapes] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)
  const [scrollViewHeight, setScrollViewHeight] = useState(0)

  const activeBar = currentBar ?? internalBar
  const isControlled = currentBar !== undefined

  const scrollRef = useRef<ScrollView>(null)
  const barLayouts = useRef<Record<number, { y: number; height: number }>>({})

  // Auto-advance bars when playing (supports varying time signatures)
  useEffect(() => {
    if (isControlled || !isPlaying) return
    const beatsPerBar = timeSignature?.[0] ?? 4
    const interval = (60000 / bpm) * beatsPerBar
    const id = setInterval(() => {
      setInternalBar((b) => (b + 1) % bars.length)
    }, interval)
    return () => clearInterval(id)
  }, [isPlaying, bars.length, isControlled, bpm, timeSignature])

  // Auto-scroll active item into view. Uses per-bar layouts in 'flow' mode
  // and per-line layouts in 'grid' mode.
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    if (layoutMode === 'flow') {
      const layout = barLayouts.current[activeBar]
      if (!layout || !scrollViewHeight) return
      const target = layout.y - scrollViewHeight / 2 + layout.height / 2
      scrollRef.current.scrollTo({ y: Math.max(0, target), animated: true })
    } else {
      const activeLineIndex = Math.floor(activeBar / barsPerLine)
      const layout = lineLayouts.current[activeLineIndex]
      if (!layout || !scrollViewHeight) return
      const target = layout.y - scrollViewHeight / 2 + layout.height / 2
      scrollRef.current.scrollTo({ y: Math.max(0, target), animated: true })
    }
  }, [activeBar, autoScroll, scrollViewHeight, barsPerLine, layoutMode])

  const handleBarPress = useCallback((bar: number) => {
    if (!isControlled) setInternalBar(bar)
    onBarPress?.(bar)
  }, [isControlled, onBarPress])

  const handleBarLayout = useCallback((barIdx: number, event: LayoutChangeEvent) => {
    const { y, height } = event.nativeEvent.layout
    barLayouts.current[barIdx] = { y, height }
  }, [])

  const handleLineLayout = useCallback((lineIdx: number, event: LayoutChangeEvent) => {
    const { y, height } = event.nativeEvent.layout
    lineLayouts.current[lineIdx] = { y, height }
  }, [])

  const displayedChord = useCallback(
    (chord: string) => transposeChord(chord, transpose),
    [transpose],
  )

  // Unique chords used in the song (transposed)
  const uniqueChords = useMemo(
    () => Array.from(new Set(
      bars.flatMap((b) => [b.chord, b.chord2].filter(Boolean) as string[]),
    )).map(displayedChord),
    [bars, displayedChord],
  )

  const activeChord = displayedChord(bars[activeBar]?.chord || '')
  const nextChord = displayedChord(
    bars[(activeBar + 1) % bars.length]?.chord || '',
  )

  // Group bars into lines of barsPerLine
  const lines = useMemo<BarData[][]>(() => {
    const grouped: BarData[][] = []
    for (let i = 0; i < bars.length; i += barsPerLine) {
      grouped.push(bars.slice(i, i + barsPerLine))
    }
    return grouped
  }, [bars, barsPerLine])

  // Track layouts for each line (for auto-scroll)
  const lineLayouts = useRef<Record<number, { y: number; height: number }>>({})

  return (
    <View className="mt-3 rounded-xl border border-wood-600/40 bg-cream-dark/45 p-4">
      {/* Header */}
      <View className="flex-row items-center justify-between mb-3">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Chords & Lyrics
        </Text>

        <View className="flex-row items-center gap-3">
          <Text className="font-mono text-[10px] text-muted-brown/70 tabular-nums">
            Bar {activeBar + 1}/{bars.length}
          </Text>
        </View>
      </View>

      {/* Section Navigator */}
      <View className="mb-3">
        <SectionNavigator
          currentBar={activeBar}
          totalBars={bars.length}
          onJump={handleBarPress}
        />
      </View>

      <View className="h-px bg-wood-600/10 mb-3" />

      {/* Toolbar: Key, Shapes, Auto-scroll */}
      <View className="flex-row items-center justify-between rounded-lg border border-wood-600/25 bg-wood-900/5 p-2 mb-4">
        <ToolControl
          label="Key"
          value={transpose === 0 ? '0' : `${transpose > 0 ? '+' : ''}${transpose}`}
          onDecrement={() => setTranspose((t) => t - 1)}
          onIncrement={() => setTranspose((t) => t + 1)}
        />

        <AnimatedPressable
          haptic="none"
          onPress={() => setShowShapes((s) => !s)}
          className={`flex-row items-center gap-1 rounded-md border px-2 py-1 ${
            showShapes
              ? 'border-amber-accent/30 bg-amber-accent/10'
              : 'border-wood-600/25 bg-wood-900/5'
          }`}
        >
          <Guitar size={10} color={showShapes ? colors.amber.light : colors.muted.brown} />
          <Text
            className={`font-mono text-[9px] uppercase tracking-wider ${
              showShapes ? 'text-amber-light' : 'text-muted-brown'
            }`}
          >
            Shapes
          </Text>
        </AnimatedPressable>

        <AnimatedPressable
          haptic="none"
          onPress={() => setAutoScroll((a) => !a)}
          className={`flex-row items-center gap-1 rounded-md border px-2 py-1 ${
            autoScroll
              ? 'border-amber-accent/30 bg-amber-accent/10'
              : 'border-wood-600/25 bg-wood-900/5'
          }`}
        >
          {autoScroll ? (
            <Lock size={10} color={autoScroll ? colors.amber.light : colors.muted.brown} />
          ) : (
            <Unlock size={10} color={colors.muted.brown} />
          )}
          <Text
            className={`font-mono text-[9px] uppercase tracking-wider ${
              autoScroll ? 'text-amber-light' : 'text-muted-brown'
            }`}
          >
            Scroll
          </Text>
        </AnimatedPressable>
      </View>

       {/* Section label (if provided) */}
       {label && (
         <View className="mb-2 flex-row items-center gap-1.5">
           <Text className="font-sans-medium text-[10px] uppercase tracking-wider text-muted-brown/60">
             [{label}]
           </Text>
           {labelConfidence != null && labelConfidence < 0.6 && (
             <Text className="font-mono text-[9px] text-danger/60">(low confidence)</Text>
           )}
         </View>
       )}

        {/* Main content: scrollable sheet + optional right sidebar for used chords */}
        <View className="flex-row items-start gap-4">
          <View className="flex-1">
            <ScrollView
              ref={scrollRef}
              showsVerticalScrollIndicator={false}
              className="max-h-[260px]"
              onLayout={(e) => setScrollViewHeight(e.nativeEvent.layout.height)}
            >
              {layoutMode === 'flow' ? (
                <View className="flex-row flex-wrap pb-4">
                  {bars.map((bar, globalBarIdx) => {
                    const isActive = globalBarIdx === activeBar
                    const chord = displayedChord(bar.chord)
                    const chord2 = bar.chord2 ? displayedChord(bar.chord2) : undefined

                    return (
                      <AnimatedPressable
                        key={`bar-${globalBarIdx}`}
                        haptic="none"
                        onPress={() => handleBarPress(globalBarIdx)}
                        onLongPress={onBarLongPress ? () => onBarLongPress(globalBarIdx) : undefined}
                        onLayout={(e: LayoutChangeEvent) => handleBarLayout(globalBarIdx, e)}
                        accessibilityRole="button"
                        accessibilityHint={`Bar ${globalBarIdx + 1}: ${bar.chord || '—'}. Tap to seek; long press to annotate`}
                        className="mr-3 mb-3"
                      >
                        {/* Chord container - left aligned */}
                        <View className="mb-0.5 flex-row items-baseline gap-1.5">
                          {onChordTap ? (
                            <AnimatedPressable
                              haptic="light"
                              onPress={(e) => {
                                e.stopPropagation()
                                onChordTap(globalBarIdx, bar.chord)
                              }}
                            >
                              <Text
                                className={`font-mono text-sm leading-tight tracking-tight text-left ${
                                  isActive ? 'text-amber-light font-sans-bold' : 'text-amber-accent/80'
                                }`}
                              >
                                {chord || ' '}
                              </Text>
                            </AnimatedPressable>
                          ) : (
                            <Text
                              className={`font-mono text-sm leading-tight tracking-tight text-left ${
                                isActive ? 'text-amber-light font-sans-bold' : 'text-amber-accent/80'
                              }`}
                            >
                              {chord || ' '}
                            </Text>
                          )}
                          {bar.roman ? (
                            <Text className="font-sans text-[10px] leading-tight tracking-tight text-left text-muted-brown">
                              {bar.roman}
                            </Text>
                          ) : null}
                          {chord2 && (
                            <Text className="font-mono text-xs leading-tight tracking-tight text-left text-amber-accent/50">
                              {chord2}
                            </Text>
                          )}
                        </View>

                        {/* Lyrics */}
                        <Text
                          className={`font-serif text-sm leading-snug text-left ${
                            isActive ? 'text-wood-900' : 'text-muted-brown'
                          }`}
                        >
                          {bar.text ?? ' '}
                        </Text>

                        <ActiveBarMarker isActive={isActive} />
                      </AnimatedPressable>
                    )
                  })}
                </View>
              ) : (
                // grid layout (legacy) - keep existing per-line rendering
                <View>
                  {lines.map((line, lineIdx) => (
                    <View
                      key={`line-${lineIdx}`}
                      onLayout={(e: LayoutChangeEvent) => handleLineLayout(lineIdx, e)}
                      className="flex-row mb-2"
                    >
                      {line.map((bar, barIdx) => {
                        const globalBarIdx = lineIdx * barsPerLine + barIdx
                        const isActive = globalBarIdx === activeBar
                        const chord = displayedChord(bar.chord)
                        const chord2 = bar.chord2 ? displayedChord(bar.chord2) : undefined

                        return (
                          <AnimatedPressable
                            key={`bar-${globalBarIdx}`}
                            haptic="none"
                            onPress={() => handleBarPress(globalBarIdx)}
                            onLongPress={onBarLongPress ? () => onBarLongPress(globalBarIdx) : undefined}
                            onLayout={(e: LayoutChangeEvent) => handleBarLayout(globalBarIdx, e)}
                            accessibilityRole="button"
                            accessibilityHint={`Bar ${globalBarIdx + 1}: ${bar.chord || '—'}. Tap to seek; long press to annotate`}
                            className="flex-1 px-1"
                          >
                            {/* Chord line */}
                            <View className="mb-0.5">
                              <Text
                                className={`font-mono text-xs leading-tight tracking-tight text-center ${
                                  isActive ? 'text-amber-light font-sans-bold' : 'text-amber-accent/80'
                                }`}
                              >
                                {chord || '—'}
                              </Text>
                            </View>
                            {bar.roman ? (
                              <View className="mb-0.5">
                                <Text className="font-sans text-[10px] leading-tight tracking-tight text-center text-muted-brown">
                                  {bar.roman}
                                </Text>
                              </View>
                            ) : null}
                            {chord2 && (
                              <View className="mb-0.5">
                                <Text className="font-mono text-[10px] leading-tight tracking-tight text-center text-amber-accent/50">
                                  {chord2}
                                </Text>
                              </View>
                            )}

                            {/* Lyrics line */}
                            {bar.text ? (
                              <Text
                                className={`font-serif text-sm leading-snug text-center ${
                                  isActive ? 'text-wood-900' : 'text-muted-brown'
                                }`}
                              >
                                {bar.text}
                              </Text>
                            ) : (
                              <Text className="font-serif text-sm leading-snug opacity-0"> </Text>
                            )}

                            <ActiveBarMarker isActive={isActive} />
                          </AnimatedPressable>
                        )
                      })}
                    </View>
                  ))}
                </View>
              )}
            </ScrollView>

            {/* Now Playing preview under the sheet */}
            {showShapes && (
              <View className="mt-4 pt-3 border-t border-wood-600/15">
                <Text className="font-sans-medium text-[10px] uppercase tracking-wider text-muted-brown/80 mb-2">
                  Now Playing
                </Text>
                <View className="flex-row items-end gap-3">
                  <FadeView fadeKey={`active-${activeChord}`}>
                    <ChordDiagram name={activeChord} size="md" isActive />
                  </FadeView>
                  <View className="opacity-60">
                    <Text className="font-mono text-[9px] uppercase tracking-wider text-muted-brown mb-1">
                      Next
                    </Text>
                    <FadeView fadeKey={`next-${nextChord}`}>
                      <ChordDiagram name={nextChord} size="sm" />
                    </FadeView>
                  </View>
                </View>
              </View>
            )}
          </View>

          {/* Right-hand sidebar with used chord shapes */}
          {showShapes && (
            <View className="w-36 min-w-0 pt-1">
              <Text className="font-sans-medium text-[10px] uppercase tracking-wider text-muted-brown/80 mb-2">
                Used In Song
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {uniqueChords.map((c) => (
                  <View key={c} className={c === activeChord ? '' : 'opacity-50'}>
                    <ChordDiagram name={c} size="sm" isActive={c === activeChord} />
                  </View>
                ))}
              </View>
            </View>
          )}
        </View>
    </View>
  )
}

function ToolControl({
  label,
  value,
  onDecrement,
  onIncrement,
}: {
  label: string
  value: string
  onDecrement: () => void
  onIncrement: () => void
}) {
  return (
    <View className="flex-row items-center gap-1.5">
      <Text className="font-mono text-[9px] uppercase tracking-wider text-muted-brown">
        {label}
      </Text>
      <View className="flex-row items-center rounded-md border border-wood-600/25 bg-wood-900/5">
        <AnimatedPressable
          haptic="none"
          onPress={onDecrement}
          className="w-6 h-6 items-center justify-center"
        >
          <Minus size={10} color={colors.muted.brown} />
        </AnimatedPressable>
        <Text className="font-mono text-[10px] text-wood-900 w-8 text-center tabular-nums">
          {value}
        </Text>
        <AnimatedPressable
          haptic="none"
          onPress={onIncrement}
          className="w-6 h-6 items-center justify-center"
        >
          <Plus size={10} color={colors.muted.brown} />
        </AnimatedPressable>
      </View>
    </View>
  )
}

function ActiveBarMarker({ isActive }: { isActive?: boolean }) {
  const opacity = useSharedValue(isActive ? 1 : 0)
  const scaleX = useSharedValue(isActive ? 1 : 0.3)

  useEffect(() => {
    opacity.value = withTiming(isActive ? 1 : 0, { duration: ACTIVE_BAR_ANIM_DURATION })
    scaleX.value = withSpring(isActive ? 1 : 0.3, spring.gentle)
  }, [isActive, opacity, scaleX])

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ scaleX: scaleX.value }],
  }))

  return (
    <Animated.View
      style={[
        style,
        {
          height: 2,
          backgroundColor: colors.amber.accent,
          marginTop: 6,
          borderRadius: 1,
          shadowColor: colors.amber.accent,
          shadowOpacity: 0.5,
          shadowRadius: 4,
          shadowOffset: { width: 0, height: 0 },
        },
      ]}
    />
  )
}

function FadeView({ children, fadeKey }: { children: React.ReactNode; fadeKey?: string }) {
  const opacity = useSharedValue(0)
  const translateY = useSharedValue(6)

  useEffect(() => {
    opacity.value = 0
    translateY.value = 6
    opacity.value = withTiming(1, { duration: timing.normal })
    translateY.value = withTiming(0, { duration: timing.normal })
  }, [fadeKey, opacity, translateY])

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }))

  return <Animated.View style={style}>{children}</Animated.View>
}

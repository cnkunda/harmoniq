import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LayoutChangeEvent, ScrollView, Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated'
import { Lock, Minus, Play, Plus, Pause, Unlock } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { BeatCounter } from './BeatCounter'
import { ChordDiagram } from './ChordDiagram'
import { SectionNavigator } from './SectionNavigator'

import colors from '@/src/constants/colors'
import { spring, timing } from '@/src/constants/animations'

export interface BarData {
  chord: string
  chord2?: string
  text?: string
}

interface ChordsAndLyricsProps {
  bars: BarData[]
  currentBar?: number
  bpm?: number
  onBarPress?: (barIndex: number) => void
  onBarLongPress?: (barIndex: number) => void
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
  onBarPress,
  onBarLongPress,
}: ChordsAndLyricsProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [internalBar, setInternalBar] = useState(0)
  const [transpose, setTranspose] = useState(0)
  const [capo, setCapo] = useState(0)
  const [autoScroll, setAutoScroll] = useState(true)
  const [scrollViewHeight, setScrollViewHeight] = useState(0)

  const activeBar = currentBar ?? internalBar
  const isControlled = currentBar !== undefined

  const scrollRef = useRef<ScrollView>(null)
  const barLayouts = useRef<Record<number, { y: number; height: number }>>({})

  // Auto-advance bars when playing
  useEffect(() => {
    if (isControlled || !isPlaying) return
    const beatsPerBar = 4
    const interval = (60000 / bpm) * beatsPerBar
    const id = setInterval(() => {
      setInternalBar((b) => (b + 1) % bars.length)
    }, interval)
    return () => clearInterval(id)
  }, [isPlaying, bars.length, isControlled, bpm])

  // Auto-scroll active bar into view
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    const layout = barLayouts.current[activeBar]
    if (!layout || !scrollViewHeight) return
    const target = layout.y - scrollViewHeight / 2 + layout.height / 2
    scrollRef.current.scrollTo({ y: Math.max(0, target), animated: true })
  }, [activeBar, autoScroll, scrollViewHeight])

  const handleBarPress = useCallback((bar: number) => {
    if (!isControlled) setInternalBar(bar)
    onBarPress?.(bar)
  }, [isControlled, onBarPress])

  const handleBarLayout = useCallback((barIdx: number, event: LayoutChangeEvent) => {
    const { y, height } = event.nativeEvent.layout
    barLayouts.current[barIdx] = { y, height }
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

  return (
    <View className="mt-3 rounded-xl border border-wood-700/40 bg-wood-800/40 p-4">
      {/* Header */}
      <View className="flex-row items-center justify-between mb-3">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Chords & Lyrics
        </Text>

        <View className="flex-row items-center gap-3">
          <BeatCounter bpm={bpm} isPlaying={isPlaying} resetKey={activeBar} />
          <Text className="font-mono text-[10px] text-muted-brown/70 tabular-nums">
            Bar {activeBar + 1}/{bars.length}
          </Text>
          {!isControlled && (
            <AnimatedPressable
              haptic="none"
              onPress={() => setIsPlaying((p) => !p)}
              accessibilityLabel={isPlaying ? 'Pause' : 'Play'}
              className="w-7 h-7 items-center justify-center rounded-full border border-wood-600/60 bg-wood-900/70"
            >
              {isPlaying ? (
                <Pause size={12} color={colors.amber.accent} />
              ) : (
                <Play size={12} color={colors.amber.accent} style={{ marginLeft: 1 }} />
              )}
            </AnimatedPressable>
          )}
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

      {/* Toolbar: Transpose, Capo, Auto-scroll */}
      <View className="flex-row items-center justify-between rounded-lg border border-wood-700/30 bg-wood-900/30 p-2 mb-4">
        <ToolControl
          label="Key"
          value={transpose === 0 ? '0' : `${transpose > 0 ? '+' : ''}${transpose}`}
          onDecrement={() => setTranspose((t) => t - 1)}
          onIncrement={() => setTranspose((t) => t + 1)}
        />

        <ToolControl
          label="Capo"
          value={capo === 0 ? 'Off' : `${capo}fr`}
          onDecrement={() => setCapo((c) => Math.max(0, c - 1))}
          onIncrement={() => setCapo((c) => Math.min(12, c + 1))}
        />

        <AnimatedPressable
          haptic="none"
          onPress={() => setAutoScroll((a) => !a)}
          className={`flex-row items-center gap-1 rounded-md border px-2 py-1 ${
            autoScroll
              ? 'border-amber-accent/30 bg-amber-accent/10'
              : 'border-wood-700/50 bg-wood-900/40'
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

      {/* Scrollable bar list */}
      <ScrollView
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
        className="max-h-[260px]"
        onLayout={(e) => setScrollViewHeight(e.nativeEvent.layout.height)}
      >
        <View className="flex-row flex-wrap py-2" style={{ gap: 16 }}>
          {bars.map((bar, idx) => {
            const isActive = idx === activeBar
            const chord = displayedChord(bar.chord)
            const chord2 = bar.chord2 ? displayedChord(bar.chord2) : undefined

            return (
              <AnimatedPressable
                key={idx}
                haptic="none"
                onPress={() => handleBarPress(idx)}
                onLongPress={onBarLongPress ? () => onBarLongPress(idx) : undefined}
                onLayout={(e: LayoutChangeEvent) => handleBarLayout(idx, e)}
                accessibilityRole="button"
                accessibilityHint={`Bar ${idx + 1}: ${bar.chord || '—'}. Tap to seek; long press to annotate`}
                className="relative"
              >
                {/* Chord row */}
                <View className="flex-row items-end mb-1" style={{ gap: 6 }}>
                  <Text
                    className={`font-mono text-xs leading-none tracking-tight ${
                      isActive ? 'text-amber-light' : 'text-amber-accent/80'
                    }`}
                  >
                    {chord}
                  </Text>
                  {chord2 && (
                    <Text
                      className={`font-mono text-xs leading-none tracking-tight ${
                        isActive ? 'text-amber-light' : 'text-amber-accent/60'
                      }`}
                    >
                      {chord2}
                    </Text>
                  )}
                </View>

                {/* Lyric */}
                {bar.text ? (
                  <Text
                    className={`font-serif text-base leading-snug ${
                      isActive ? 'text-ivory' : 'text-cream/70'
                    }`}
                  >
                    {bar.text}
                  </Text>
                ) : null}

                {/* Active bar underline marker */}
                {isActive && (
                  <ActiveBarMarker />
                )}
              </AnimatedPressable>
            )
          })}
        </View>
      </ScrollView>

      {/* Active / Next Chord Diagram Preview */}
      <View className="mt-4 pt-3 border-t border-wood-700/40">
        <View className="flex-row gap-4">
          {/* Now Playing */}
          <View className="flex-1">
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

          {/* Used In Song */}
          <View className="flex-1 min-w-0">
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
        </View>
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
      <View className="flex-row items-center rounded-md border border-wood-700/50 bg-wood-900/60">
        <AnimatedPressable
          haptic="none"
          onPress={onDecrement}
          className="w-6 h-6 items-center justify-center"
        >
          <Minus size={10} color={colors.muted.brown} />
        </AnimatedPressable>
        <Text className="font-mono text-[10px] text-cream w-8 text-center tabular-nums">
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

function ActiveBarMarker() {
  const opacity = useSharedValue(0)
  const scaleX = useSharedValue(0.3)

  useEffect(() => {
    opacity.value = withTiming(1, { duration: ACTIVE_BAR_ANIM_DURATION })
    scaleX.value = withSpring(1, spring.gentle)
  }, [opacity, scaleX])

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

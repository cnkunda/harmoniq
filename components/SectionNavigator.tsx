import { useMemo, useRef, useCallback, useEffect } from 'react'
import { ScrollView, Text, View } from 'react-native'

import { AnimatedPressable } from './AnimatedPressable'

const CHIP_W = 32
const CHIP_GAP = 4
const VISIBLE_COUNT = 11

interface SectionNavigatorProps {
  currentBar: number
  totalBars: number
  onJump: (barIndex: number) => void
}

export function SectionNavigator({ currentBar, totalBars, onJump }: SectionNavigatorProps) {
  const scrollRef = useRef<ScrollView>(null)

  const windowStart = useMemo(() => {
    const half = Math.floor(VISIBLE_COUNT / 2)
    const raw = currentBar - half
    return Math.max(0, Math.min(raw, Math.max(0, totalBars - VISIBLE_COUNT)))
  }, [currentBar, totalBars])

  const visibleBars = useMemo(() => {
    const count = Math.min(VISIBLE_COUNT, totalBars)
    return Array.from({ length: count }, (_, i) => windowStart + i)
  }, [windowStart, totalBars])

  // Scroll to center the active chip when currentBar changes
  useEffect(() => {
    const activeInWindow = visibleBars.indexOf(currentBar)
    if (activeInWindow < 0 || !scrollRef.current) return
    const scrollToX = activeInWindow * (CHIP_W + CHIP_GAP) - (VISIBLE_COUNT * (CHIP_W + CHIP_GAP)) / 2 + CHIP_W / 2
    scrollRef.current.scrollTo({ x: Math.max(0, scrollToX), animated: true })
  }, [currentBar, visibleBars])

  const handleChipPress = useCallback((bar: number) => {
    onJump(bar)
  }, [onJump])

  return (
    <ScrollView
      ref={scrollRef}
      horizontal
      showsHorizontalScrollIndicator={false}
      className="py-1"
    >
      <View className="flex-row" style={{ gap: CHIP_GAP }}>
        {visibleBars.map((bar) => {
          const isActive = bar === currentBar
          return (
            <AnimatedPressable
              key={bar}
              haptic="none"
              onPress={() => handleChipPress(bar)}
              className={`w-8 h-8 items-center justify-center rounded-full border ${
                isActive
                  ? 'border-amber-accent bg-amber-accent/20'
                  : 'border-wood-600/40 bg-wood-900/30'
              }`}
              accessibilityRole="button"
              accessibilityHint={`Go to bar ${bar + 1}`}
            >
              <Text
                className={`font-mono text-[11px] ${
                  isActive ? 'text-amber-accent font-medium' : 'text-muted-brown'
                }`}
              >
                {bar + 1}
              </Text>
            </AnimatedPressable>
          )
        })}
      </View>
    </ScrollView>
  )
}

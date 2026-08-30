import { useEffect, useMemo, useRef, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'

export type LyricWord = {
  word: string
  timeSec: number
}

type LyricsStripProps = {
  words: LyricWord[]
  playbackSec: number
  hideHeading?: boolean
}

function activeIndexForTime(words: LyricWord[], t: number): number {
  if (words.length === 0) return -1
  for (let i = words.length - 1; i >= 0; i -= 1) {
    if (t >= words[i].timeSec) return i
  }
  return -1
}

export function LyricsStrip({ words, playbackSec, hideHeading }: LyricsStripProps) {
  const activeIndex = useMemo(() => activeIndexForTime(words, playbackSec), [words, playbackSec])
  const scrollViewRef = useRef<ScrollView>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [wordLayouts, setWordLayouts] = useState<{ [key: number]: { x: number; width: number } }>({})

  // Scroll to keep active word visible (web implementation using DOM)
  useEffect(() => {
    if (containerRef.current && activeIndex >= 0 && wordLayouts[activeIndex]) {
      const { x, width } = wordLayouts[activeIndex]
      const container = containerRef.current
      const containerWidth = container.clientWidth
      
      // Scroll to center the active word
      const targetScroll = x - containerWidth / 2 + width / 2 - 16 // Adjust for padding
      container.scrollTo({
        left: Math.max(0, targetScroll),
        behavior: 'smooth',
      })
    }
  }, [activeIndex, wordLayouts])

  const handleWordLayout = (index: number, event: any) => {
    if (event?.nativeEvent?.layout) {
      const { x, width } = event.nativeEvent.layout
      setWordLayouts((prev) => ({
        ...prev,
        [index]: { x, width },
      }))
    }
  }

  if (words.length === 0) {
    if (hideHeading) return null
    return (
      <Text className="mt-2 font-sans text-xs text-wood-600">
        Lyrics unavailable for this section.
      </Text>
    )
  }

  return (
    <View className={hideHeading ? "w-full" : "mt-2 w-full"}>
      {!hideHeading && (
        <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-wood-600">
          Lyrics
        </Text>
      )}
      <div
        ref={containerRef}
        style={{
          display: 'flex',
          overflowX: 'auto',
          overflowY: 'hidden',
          paddingLeft: 16,
          paddingRight: 16,
          scrollBehavior: 'smooth',
        }}
      >
        <View className="flex-row items-center gap-1.5 pb-1">
          {words.map((w, i) => (
            <Text
              key={`${i}-${w.timeSec}`}
              onLayout={(event) => handleWordLayout(i, event)}
              className={
                i === activeIndex
                  ? 'font-sans-medium text-base text-amber-accent'
                  : i < activeIndex
                  ? 'font-sans text-sm text-wood-600'
                  : 'font-sans text-sm text-wood-600'
              }
            >
              {w.word}
            </Text>
          ))}
        </View>
      </div>
    </View>
  )
}


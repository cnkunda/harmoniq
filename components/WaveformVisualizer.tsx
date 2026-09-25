import { useMemo } from 'react'
import { View } from 'react-native'

import colors from '@/src/constants/colors'

export interface WaveformVisualizerProps {
  isPlaying?: boolean
  progress?: number
  highlightRegion?: [number, number]
  className?: string
}

const BAR_COUNT = 60

function seededValue(index: number, seed: number): number {
  const x = Math.sin(index * 127.1 + seed * 311.7) * 43758.5453
  return x - Math.floor(x)
}

export function WaveformVisualizer({
  isPlaying = false,
  progress = 0,
  highlightRegion,
  className = '',
}: WaveformVisualizerProps) {
  const barData = useMemo(() => {
    return Array.from({ length: BAR_COUNT }).map((_, i) => {
      const sin = Math.sin(i * 0.2) * 0.5 + 0.5
      const cos = Math.cos(i * 0.5) * 0.5 + 0.5
      const base = Math.max(0.1, sin * 0.6 + cos * 0.4)
      const breathe = 0.85 + seededValue(i, 42) * 0.3
      return { base, breathe }
    })
  }, [])

  return (
    <View
      className={`w-full h-24 flex-row items-end overflow-hidden rounded-xl border border-wood-700/40 bg-wood-800/50 p-2 ${className}`}
    >
      <View
        className="absolute inset-0 z-10 border-r border-amber-accent/40 bg-amber-accent/10"
        style={{ width: `${progress * 100}%` }}
        pointerEvents="none"
      />

      {highlightRegion && (
        <View
          className="absolute inset-0 z-0 rounded-sm border-x border-amber-light/25 bg-amber-light/10"
          style={{
            left: `${highlightRegion[0] * 100}%`,
            width: `${(highlightRegion[1] - highlightRegion[0]) * 100}%`,
          }}
          pointerEvents="none"
        />
      )}

      {barData.map(({ base, breathe }, i) => {
        const isPast = i / BAR_COUNT <= progress
        return (
          <View
            key={i}
            className={`mx-[0.5px] flex-1 rounded-t-sm ${isPast ? 'bg-amber-accent' : 'bg-wood-600'}`}
            style={{
              height: isPlaying ? `${base * breathe * 100}%` : `${base * 100}%`,
              minHeight: 4,
              opacity: isPast ? 1 : 0.5,
            }}
          />
        )
      })}
    </View>
  )
}

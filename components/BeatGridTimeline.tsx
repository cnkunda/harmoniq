/** Commit 109: Beat grid timeline visualization with beat/downbeat markers and bar lines. */

import { useMemo } from 'react'
import { View } from 'react-native'
import Svg, { Line, Polyline } from 'react-native-svg'

import { colors } from '@/src/constants/colors'
import type { BeatGrid } from '@/src/types'

export interface BeatGridTimelineProps {
  beatGrid: BeatGrid
  durationSec: number
  playbackPositionSec?: number
  height?: number
  width?: number
}

/**
 * Horizontal timeline showing beat markers, downbeat highlights, and bar lines.
 * Downbeats are detected from `beatGrid.time_signature.numerator` (not hardcoded 4/4).
 */
export function BeatGridTimeline({
  beatGrid,
  durationSec,
  playbackPositionSec = 0,
  height = 40,
  width = 300,
}: BeatGridTimelineProps) {
  const { beats, downbeats } = beatGrid

  // Map beat timestamps to x positions (0..width)
  const beatLines = useMemo(() => {
    if (!beats || beats.length === 0 || durationSec <= 0) return []
    const downbeatSet = new Set(downbeats?.map((d) => d.toFixed(4)))
    return beats.map((t) => {
      const x = (t / durationSec) * width
      const isDownbeat = downbeatSet.has(t.toFixed(4))
      return { x, isDownbeat }
    })
  }, [beats, downbeats, durationSec, width])

  // Map bar lines (downbeats)
  const barLines = useMemo(() => {
    if (!downbeats || downbeats.length === 0 || durationSec <= 0) return []
    return downbeats.map((t) => (t / durationSec) * width)
  }, [downbeats, durationSec, width])

  // Playback playhead position
  const playheadX = durationSec > 0 ? (playbackPositionSec / durationSec) * width : 0

  return (
    <View className="rounded-md border border-wood-600/45 bg-ivory">
      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* Bar lines (vertical lines at downbeat positions) */}
        {barLines.map((x, i) => (
          <Line
            key={`bar-${i}`}
            x1={x}
            y1={0}
            x2={x}
            y2={height}
            stroke={colors.muted.brown}
            strokeOpacity={0.4}
            strokeWidth={1.0}
          />
        ))}

        {/* Beat ticks (smaller marks at beat positions) */}
        {beatLines.map(({ x, isDownbeat }, i) => (
          <Line
            key={`beat-${i}`}
            x1={x}
            y1={isDownbeat ? 0 : height * 0.3}
            x2={x}
            y2={height}
            stroke={isDownbeat ? colors.amber.accent : colors.muted.brown}
            strokeOpacity={isDownbeat ? 0.8 : 0.3}
            strokeWidth={isDownbeat ? 1.2 : 0.5}
          />
        ))}

        {/* Playback playhead */}
        {playbackPositionSec > 0 && playbackPositionSec < durationSec && (
          <Polyline
            points={`${playheadX},0 ${playheadX},${height}`}
            fill="none"
            stroke={colors.amber.accent}
            strokeOpacity={0.9}
            strokeWidth={1.5}
          />
        )}
      </Svg>
    </View>
  )
}

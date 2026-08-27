import React, { useMemo } from 'react'
import { View, Text } from 'react-native'
import Svg, { Line, Rect, Text as SvgText } from 'react-native-svg'
import colors from '@/src/constants/colors'

export interface BeatGridTimelineProps {
  beats: number[]
  downbeats: number[]
  timeSignature: { numerator: number; denominator: number }
  durationSeconds: number
  width?: number
  height?: number
  currentTime?: number
  chordEvents?: Array<{ timestamp: number; chord: string }>
  style?: object
}

const BEAT_HEIGHT = 6
const DOWNBEAT_HEIGHT = 14
const BAR_LINE_HEIGHT = 22
const CHORD_ROW_HEIGHT = 20
const PADDING_LEFT = 8
const PADDING_RIGHT = 8

export function BeatGridTimeline({
  beats,
  downbeats,
  timeSignature,
  durationSeconds,
  width = 340,
  height = 80,
  currentTime,
  chordEvents,
  style,
}: BeatGridTimelineProps) {
  const chartWidth = width - PADDING_LEFT - PADDING_RIGHT
  const downbeatSet = useMemo(() => new Set(downbeats.map((d) => Math.round(d * 1000))), [downbeats])

  const timeToX = (t: number) => {
    if (durationSeconds <= 0) return PADDING_LEFT
    return PADDING_LEFT + (t / durationSeconds) * chartWidth
  }

  const beatLines = useMemo(() => {
    return beats.map((t) => ({
      x: timeToX(t),
      isDownbeat: downbeatSet.has(Math.round(t * 1000)),
    }))
  }, [beats, downbeatSet, durationSeconds])

  const barLines = useMemo(() => {
    return downbeats.map((t) => timeToX(t))
  }, [downbeats, durationSeconds])

  const chords = useMemo(() => {
    if (!chordEvents?.length) return []
    return chordEvents.map((e) => ({
      x: timeToX(e.timestamp),
      label: e.chord,
    }))
  }, [chordEvents, durationSeconds])

  const playheadX = currentTime != null ? timeToX(currentTime) : null

  const totalHeight = chordEvents?.length ? height + CHORD_ROW_HEIGHT : height

  return (
    <View style={[{ width, height: totalHeight }, style]}>
      <Svg width={width} height={totalHeight}>
        {/* Bar lines */}
        {barLines.map((x, i) => (
          <Line
            key={`bar-${i}`}
            x1={x}
            y1={0}
            x2={x}
            y2={totalHeight}
            stroke={colors.wood[600]}
            strokeWidth={1.5}
            strokeDasharray="4,2"
          />
        ))}

        {/* Beat ticks */}
        {beatLines.map(({ x, isDownbeat }, i) => (
          <Line
            key={`beat-${i}`}
            x1={x}
            y1={totalHeight - (isDownbeat ? DOWNBEAT_HEIGHT : BEAT_HEIGHT)}
            x2={x}
            y2={totalHeight}
            stroke={isDownbeat ? colors.amber.accent : colors.muted.light}
            strokeWidth={isDownbeat ? 2 : 1}
          />
        ))}

        {/* Chord labels row */}
        {chords.map((c, i) => (
          <React.Fragment key={`chord-${i}`}>
            <Rect
              x={c.x - 2}
              y={0}
              width={Math.max(20, (chartWidth / Math.max(chords.length, 1)) * 0.8)}
              height={CHORD_ROW_HEIGHT - 2}
              rx={3}
              fill={colors.wood[700]}
              opacity={0.8}
            />
            <SvgText
              x={c.x + 2}
              y={CHORD_ROW_HEIGHT - 6}
              fontSize={9}
              fill={colors.cream}
              fontFamily="monospace"
            >
              {c.label}
            </SvgText>
          </React.Fragment>
        ))}

        {/* Playhead */}
        {playheadX != null && (
          <Line
            x1={playheadX}
            y1={0}
            x2={playheadX}
            y2={totalHeight}
            stroke={colors.amber.accent}
            strokeWidth={2}
          />
        )}
      </Svg>
    </View>
  )
}

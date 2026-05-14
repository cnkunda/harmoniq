import Slider from '@react-native-community/slider'
import { useMemo } from 'react'
import { Text, View } from 'react-native'
import { Circle, Line, Svg } from 'react-native-svg'

import colors from '@/src/constants/colors'
import { chordToFretboardCells, formatChordDisplay } from '@/src/music/chordVoicing'
import type { LessonJSON } from '@/src/types'

const FRET_COUNT = 5
const STRING_COUNT = 6
const CELL_W = 44
const CELL_H = 36
const PAD_X = 16
const PAD_Y = 12
const SVG_W = PAD_X * 2 + CELL_W * (FRET_COUNT + 1)
const SVG_H = PAD_Y * 2 + CELL_H * (STRING_COUNT - 1)

type OrientFretboardPlayerProps = {
  lesson: LessonJSON
  positionSec: number
  orientAnnotation: string | null
  onSeek: (sec: number) => void
}

function currentChordAtPosition(
  chordEvents: Array<{ timestamp: number; chord: string }>,
  sec: number,
): string | null {
  let best: string | null = null
  for (const ev of chordEvents) {
    if (ev.timestamp <= sec) best = ev.chord
    else break
  }
  return best
}

export function OrientFretboardPlayer({
  lesson,
  positionSec,
  orientAnnotation,
  onSeek,
}: OrientFretboardPlayerProps) {
  const chordEvents = lesson.chord_timeline?.events ?? []
  const currentChord = useMemo(
    () => currentChordAtPosition(chordEvents, positionSec),
    [chordEvents, positionSec],
  )
  const displayChord = useMemo(
    () => (currentChord ? formatChordDisplay(currentChord) : '—'),
    [currentChord],
  )

  const fretCells = useMemo(() => {
    if (!currentChord) return []
    return chordToFretboardCells(currentChord, 'compact', 'open')
  }, [currentChord])

  const duration = useMemo(() => {
    if (chordEvents.length < 2) return 30
    return Math.max(30, chordEvents[chordEvents.length - 1]!.timestamp + 4)
  }, [chordEvents])

  const stringEndpoints = useMemo(() => {
    const lines: Array<{ x1: number; y1: number; x2: number; y2: number }> = []
    for (let s = 0; s < STRING_COUNT; s++) {
      const y = PAD_Y + s * CELL_H
      lines.push({ x1: PAD_X, y1: y, x2: PAD_X + CELL_W * (FRET_COUNT + 1), y2: y })
    }
    return lines
  }, [])

  const fretLines = useMemo(() => {
    const lines: Array<{ x: number }> = []
    for (let f = 0; f <= FRET_COUNT + 1; f++) {
      lines.push({ x: PAD_X + f * CELL_W })
    }
    return lines
  }, [])

  const noteDots = useMemo(() => {
    return fretCells.map((cell) => {
      const row = 6 - cell.string
      const x = PAD_X + cell.fret * CELL_W + CELL_W / 2
      const y = PAD_Y + row * CELL_H + CELL_H / 2
      return { x, y, interval: cell.interval }
    })
  }, [fretCells])

  const minutes = Math.floor(positionSec / 60)
  const seconds = Math.floor(positionSec % 60)
  const timeLabel = `${minutes}:${seconds.toString().padStart(2, '0')}`
  const totalMinutes = Math.floor(duration / 60)
  const totalSeconds = Math.floor(duration % 60)
  const totalLabel = `${totalMinutes}:${totalSeconds.toString().padStart(2, '0')}`

  return (
    <View className="mt-4 overflow-hidden rounded-xl border border-wood-600/30 bg-wood-800/50">
      {/* Chord name header */}
      <View className="items-center border-b border-wood-700/30 px-4 py-3">
        <Text className="font-serif text-2xl tracking-wider text-amber-accent">{displayChord}</Text>
      </View>

      {/* Fretboard SVG */}
      <View className="items-center px-2 pt-3">
        <Svg width={SVG_W} height={SVG_H} viewBox={`0 0 ${SVG_W} ${SVG_H}`}>
          {stringEndpoints.map((line, i) => (
            <Line
              key={`s${i}`}
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
              stroke={colors.wood[500]}
              strokeWidth={i === 0 ? 2.5 : 1.5}
              strokeLinecap="round"
            />
          ))}
          {fretLines.map((fl, i) => (
            <Line
              key={`f${i}`}
              x1={fl.x}
              y1={PAD_Y}
              x2={fl.x}
              y2={PAD_Y + CELL_H * (STRING_COUNT - 1)}
              stroke={i === 0 || i === fretLines.length - 1 ? colors.wood[500] : colors.wood[600]}
              strokeWidth={i === 0 || i === fretLines.length - 1 ? 3 : 1}
              strokeLinecap="round"
            />
          ))}
          {noteDots.map((dot, i) => (
            <Circle
              key={i}
              cx={dot.x}
              cy={dot.y}
              r={7}
              fill={dot.interval === 0 ? colors.amber.accent : `${colors.amber.accent}80`}
              stroke={colors.amber.accent}
              strokeWidth={1}
            />
          ))}
        </Svg>
      </View>

      {/* Timeline seek bar */}
      <View className="flex-row items-center gap-3 px-4 pb-1 pt-2">
        <Text className="w-12 font-mono text-[11px] text-muted-brown">{timeLabel}</Text>
        <View className="flex-1">
          <Slider
            minimumValue={0}
            maximumValue={Math.max(1, duration)}
            value={Math.min(positionSec, duration)}
            onSlidingComplete={onSeek}
            minimumTrackTintColor={colors.amber.accent}
            maximumTrackTintColor={colors.wood[500]}
            thumbTintColor={colors.amber.accent}
          />
        </View>
        <Text className="w-12 text-right font-mono text-[11px] text-muted-brown">{totalLabel}</Text>
      </View>

      {/* Annotation */}
      {orientAnnotation ? (
        <View className="px-4 pb-3 pt-1">
          <Text className="font-sans text-[12px] leading-relaxed text-cream/70">{orientAnnotation}</Text>
        </View>
      ) : null}
    </View>
  )
}

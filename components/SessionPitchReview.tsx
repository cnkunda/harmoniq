import { Text, View } from 'react-native'
import Svg, { Line, Polyline } from 'react-native-svg'

import colors from '@/src/constants/colors'
import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'
import type { NoteContourSample } from '@/src/stores/useAppStore'

function midiToHz(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

const W = 112
const H = 36

function hzToY(hz: number, hzMin: number, hzMax: number): number {
  if (hzMax <= hzMin) return H / 2
  const n = (hz - hzMin) / (hzMax - hzMin)
  return H - n * (H - 4) - 2
}

function SparkRow({
  contour,
  targetMidi,
  result,
}: {
  contour: NoteContourSample[]
  targetMidi: number
  result: NoteResultLabel
}) {
  const targetHz = midiToHz(targetMidi)
  const hzVals = contour.map((c) => c.hz).filter((h) => h > 0)
  if (hzVals.length === 0) {
    return (
      <Text className="font-sans text-[10px] text-muted-brown" numberOfLines={1}>
        No pitch trace
      </Text>
    )
  }
  const hzMin = Math.min(...hzVals, targetHz) * 0.997
  const hzMax = Math.max(...hzVals, targetHz) * 1.003
  const tMax = Math.max(...contour.map((c) => c.t), 1)
  const pts = contour
    .filter((c) => c.hz > 0)
    .map((c) => {
      const x = 2 + (c.t / tMax) * (W - 4)
      const y = hzToY(c.hz, hzMin, hzMax)
      return `${x},${y}`
    })
    .join(' ')
  const yRef = hzToY(targetHz, hzMin, hzMax)
  const strokeUser = colors.amber.accent
  const strokeTarget = colors.success

  const resultLabel =
    result === 'vibrato'
      ? 'vibrato'
      : result === 'hit'
        ? 'hit'
        : result === 'close'
          ? 'close'
          : result === 'miss'
            ? 'miss'
            : String(result)

  const labelClass =
    result === 'vibrato'
      ? 'text-amber-accent'
      : result === 'hit' || result === 'close'
        ? 'text-success'
        : result === 'miss'
          ? 'text-danger'
          : 'text-muted-brown'

  return (
    <View className="mb-3 flex-row items-center gap-2">
      <Text className={`w-14 font-sans text-[10px] ${labelClass}`} numberOfLines={1}>
        {resultLabel}
      </Text>
      <Svg width={W} height={H}>
        <Line x1={2} y1={yRef} x2={W - 2} y2={yRef} stroke={strokeTarget} strokeWidth={1} opacity={0.9} />
        {pts.length > 0 ? (
          <Polyline points={pts} fill="none" stroke={strokeUser} strokeWidth={1.25} strokeLinejoin="round" />
        ) : null}
      </Svg>
    </View>
  )
}

export interface SessionPitchReviewProps {
  noteContours: NoteContourSample[][]
  noteTargetMidis: number[]
  noteResults: NoteResultLabel[]
}

/** Per-note Hz contour vs target (Hz), minimal SVG sparklines. */
export function SessionPitchReview({ noteContours, noteTargetMidis, noteResults }: SessionPitchReviewProps) {
  if (noteContours.length === 0) return null
  return (
    <View className="mt-3 rounded-lg border border-wood-600/45 bg-cream-dark/40 px-3 py-3">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Pitch contours</Text>
      <Text className="mt-1 font-sans text-[10px] text-muted-brown">
        Sage line = target Hz · Amber = your pitch (time →)
      </Text>
      <View className="mt-2">
        {noteContours.map((contour, i) => (
          <SparkRow
            key={`c-${i}`}
            contour={contour}
            targetMidi={noteTargetMidis[i] ?? 60}
            result={noteResults[i] ?? 'miss'}
          />
        ))}
      </View>
    </View>
  )
}

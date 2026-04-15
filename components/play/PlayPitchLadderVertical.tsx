import { Text, View } from 'react-native'

import { midiToScientificPitchName } from '@/components/PitchIndicator'
import { hitInnerThresholdCents } from '@/src/session/noteAccuracyBeats'

type PlayPitchLadderVerticalProps = {
  /** Merged onto the root card (e.g. `flex-1` to match sibling column height). */
  className?: string
  cents: number | null | undefined
  isActive: boolean
  adaptedCentsTolerance: number
  targetMidi: number
  nextTargetMidi?: number | null
}

const TRACK_MIN_H = 160

/**
 * Vertical cents ladder (-50..+50) with status copy (Perfect / Close / Sharp / Flat).
 */
export function PlayPitchLadderVertical({
  className,
  cents,
  isActive,
  adaptedCentsTolerance,
  targetMidi,
  nextTargetMidi,
}: PlayPitchLadderVerticalProps) {
  const innerTol = hitInnerThresholdCents(adaptedCentsTolerance)
  const clamped =
    cents != null && Number.isFinite(cents) ? Math.max(-50, Math.min(50, cents)) : 0
  /** 0 = top (+50¢), 100 = bottom (-50¢), 50 = center */
  const positionPct = 50 - clamped
  const targetSci = Number.isFinite(targetMidi) ? midiToScientificPitchName(targetMidi) : '—'
  const nextSci =
    nextTargetMidi != null && Number.isFinite(nextTargetMidi)
      ? midiToScientificPitchName(nextTargetMidi)
      : null

  let statusTitle = 'Waiting…'
  let statusSub = 'Play to see pitch feedback'
  let statusTone = 'text-muted-brown'

  if (isActive && cents != null && Number.isFinite(cents)) {
    const a = Math.abs(cents)
    if (a <= innerTol) {
      statusTitle = 'Perfect!'
      statusSub = 'Great pitch accuracy'
      statusTone = 'text-success'
    } else if (a <= adaptedCentsTolerance) {
      statusTitle = 'Close'
      statusSub = `Adjust ${cents > 0 ? 'down' : 'up'} ${Math.abs(Math.round(cents))} cents`
      statusTone = 'text-amber-accent'
    } else {
      statusTitle = cents > 0 ? 'Sharp' : 'Flat'
      statusSub = `Adjust ${cents > 0 ? 'down' : 'up'} ${Math.abs(Math.round(cents))} cents`
      statusTone = 'text-danger'
    }
  }

  const rootClass = [
    'min-h-0 flex-col rounded-xl border border-wood-600/40 bg-cream-dark/50 p-4',
    className ?? '',
  ]
    .join(' ')
    .trim()

  return (
    <View className={rootClass}>
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Live pitch vs target</Text>
      <Text className="mt-1 font-sans text-xs text-muted-brown">
        Cents are measured against the highlighted tab target above — it moves when the tab advances.
      </Text>
      <View className="mb-3 mt-3 shrink-0 flex-row items-center justify-between">
        <Text className="font-sans text-[11px] text-wood-900">Instant readout</Text>
        <Text className={`font-mono text-sm ${isActive && cents != null ? 'text-wood-900' : 'text-muted-brown'}`}>
          {isActive && cents != null && Number.isFinite(cents)
            ? `${cents >= 0 ? '+' : ''}${Math.round(cents)}¢`
            : '—'}
        </Text>
      </View>
      <View className="min-h-0 flex-1 flex-row items-stretch gap-3">
        <View
          style={{ width: 56, minHeight: TRACK_MIN_H }}
          className="max-h-full self-stretch overflow-hidden rounded-lg border border-wood-600/35 bg-wood-900/10"
        >
          <View
            className="absolute left-0 right-0 bg-success/15"
            style={{ top: '35%', height: '30%' }}
          />
          <View className="absolute left-0 right-0 border-t border-wood-600/40" style={{ top: '50%' }} />
          <Text className="absolute right-0.5 top-0.5 font-mono text-[9px] text-muted-brown">+50</Text>
          <Text className="absolute right-0.5 top-[46%] font-mono text-[9px] text-muted-brown">0</Text>
          <Text className="absolute bottom-0.5 right-0.5 font-mono text-[9px] text-muted-brown">-50</Text>
          {isActive && cents != null ? (
            <View
              className="absolute left-1 right-1 z-10 rounded-full bg-amber-accent"
              style={{ height: 10, top: `${positionPct}%`, marginTop: -5 }}
            />
          ) : null}
        </View>
        <View className="min-h-0 flex-1 justify-center">
          <Text className="font-mono text-xs text-wood-900">Target · {targetSci}</Text>
          {nextSci ? (
            <Text className="mt-0.5 font-mono text-[11px] text-muted-brown">Prior tab note · {nextSci}</Text>
          ) : null}
          <Text className={`mt-3 font-sans text-2xl font-bold ${statusTone}`}>{statusTitle}</Text>
          <Text className="mt-1 font-sans text-sm text-muted-brown">{statusSub}</Text>
        </View>
      </View>
    </View>
  )
}

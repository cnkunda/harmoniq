import { Dna } from 'lucide-react-native'
import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withSequence, withTiming } from 'react-native-reanimated'
import Svg, { Polygon, Circle as SvgCircle } from 'react-native-svg'

import { EmptyState } from '@/components/EmptyState'
import colors from '@/src/constants/colors'
import { DNA_MIN_SESSIONS, type PlayerDNA } from '@/src/music/dnaComputer'

const PC_LABELS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

function radarPoints(bias: number[], cx: number, cy: number, rMax: number, rMin: number): string {
  const parts: string[] = []
  for (let i = 0; i < 12; i += 1) {
    const ang = (i * 2 * Math.PI) / 12 - Math.PI / 2
    const mag = rMin + (rMax - rMin) * Math.max(0, Math.min(1, bias[i] ?? 0))
    const x = cx + mag * Math.cos(ang)
    const y = cy + mag * Math.sin(ang)
    parts.push(`${x.toFixed(2)},${y.toFixed(2)}`)
  }
  return parts.join(' ')
}

function TimingPendulum({ feel }: { feel: PlayerDNA['timing_feel'] }) {
  const base = feel === 'ahead' ? -20 : feel === 'behind' ? 20 : 0
  const swing = useSharedValue(base)

  useEffect(() => {
    swing.value = withRepeat(
      withSequence(
        withTiming(base + 6, { duration: 650, easing: Easing.inOut(Easing.sin) }),
        withTiming(base - 6, { duration: 650, easing: Easing.inOut(Easing.sin) }),
      ),
      -1,
      true,
    )
  }, [base, swing])

  const rodStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${swing.value}deg` }],
  }))

  return (
    <View className="h-28 items-center justify-start pt-1">
      <Animated.View style={rodStyle} className="items-center">
        <View className="h-14 w-[3px] rounded-full bg-amber-accent/85" />
        <View className="-mt-1 h-4 w-4 rounded-full border-2 border-amber-accent bg-wood-900" />
      </Animated.View>
      <Text className="mt-2 font-sans text-xs text-muted-light">
        {feel === 'ahead' ? 'Ahead of the beat' : feel === 'behind' ? 'Behind the beat' : 'Centered time feel'}
      </Text>
    </View>
  )
}

export interface RiffDNAProps {
  dna: PlayerDNA | null
}

export function RiffDNA({ dna }: RiffDNAProps) {
  if (!dna || dna.eligibleSessionCount < DNA_MIN_SESSIONS) {
    return (
      <View className="rounded-xl border border-wood-700/50 bg-wood-800/50 py-4">
        <EmptyState
          Icon={Dna}
          heading="Your playing fingerprint"
          subtext="Play 3 sessions to reveal your DNA"
        />
      </View>
    )
  }

  const topTech = Object.entries(dna.technique_frequency)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
  const maxTech = topTech.length > 0 ? Math.max(...topTech.map(([, c]) => c), 1) : 1

  const first = dna.firstRecordedDate
  let firstLabel = '—'
  if (first) {
    const d = new Date(first)
    firstLabel = Number.isNaN(d.getTime()) ? first : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <View className="gap-6 rounded-xl border border-wood-700/50 bg-wood-800/50 p-5">
      <View>
        <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-light">Pitch-class shape</Text>
        <View className="mt-3 items-center">
          <Svg width={200} height={200} viewBox="0 0 100 100">
            <SvgCircle cx={50} cy={50} r={38} fill="none" stroke={colors.wood[600]} strokeWidth={0.4} opacity={0.5} />
            <SvgCircle cx={50} cy={50} r={24} fill="none" stroke={colors.wood[600]} strokeWidth={0.35} opacity={0.35} />
            <Polygon
              points={radarPoints(dna.pitch_class_bias, 50, 50, 36, 8)}
              fill={colors.amber.accent}
              opacity={0.22}
              stroke={colors.amber.accent}
              strokeWidth={0.8}
            />
          </Svg>
        </View>
        <View className="mt-2 flex-row flex-wrap justify-center gap-x-2 gap-y-1">
          {PC_LABELS.map((lbl, i) => (
            <Text key={lbl} className="font-mono text-[10px] text-muted-light">
              {lbl}:{Math.round((dna.pitch_class_bias[i] ?? 0) * 100)}
            </Text>
          ))}
        </View>
      </View>

      <View>
        <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-light">Fret zones (low → high)</Text>
        <View className="mt-3 h-14 flex-row items-end gap-1">
          {dna.position_bias.map((v, i) => (
            <View key={i} className="flex-1 items-center justify-end">
              <View
                className="w-full rounded-t bg-amber-accent"
                style={{ height: Math.max(6, 52 * v), opacity: 0.35 + 0.65 * v }}
              />
            </View>
          ))}
        </View>
      </View>

      <View>
        <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-light">Timing pendulum</Text>
        <TimingPendulum feel={dna.timing_feel} />
      </View>

      <View>
        <Text className="font-sans-medium text-xs uppercase tracking-wider text-muted-light">Technique mix</Text>
        <View className="mt-3 gap-2">
          {topTech.length === 0 ? (
            <Text className="font-sans text-sm text-muted-light">No technique tags yet.</Text>
          ) : (
            topTech.map(([label, count]) => (
              <View key={label} className="gap-1">
                <View className="flex-row justify-between">
                  <Text className="max-w-[70%] font-sans text-xs text-cream" numberOfLines={1}>
                    {label.replace(/^jam:/, '').replace(/^lick:/, 'Lick · ')}
                  </Text>
                  <Text className="font-mono text-xs text-muted-light">{count}</Text>
                </View>
                <View className="h-2 overflow-hidden rounded-full bg-wood-900/80">
                  <View className="h-full rounded-full bg-amber-accent/90" style={{ width: `${Math.min(100, (count / maxTech) * 100)}%` }} />
                </View>
              </View>
            ))
          )}
        </View>
      </View>

      <Text className="font-sans text-xs text-muted-light">First recorded: {firstLabel}</Text>
    </View>
  )
}

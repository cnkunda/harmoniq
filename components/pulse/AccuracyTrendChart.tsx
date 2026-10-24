import { useCallback, useMemo, useState } from 'react'
import { Text, View } from 'react-native'
import Svg, {
  Circle,
  Defs,
  Line,
  LinearGradient as SvgLinearGradient,
  Polygon,
  Polyline,
  Stop,
} from 'react-native-svg'

import { colors } from '@/src/constants/colors'
import type { PulseAccuracyPoint } from '@/src/progress/pulseData'

const CHART_HEIGHT = 156
const TOP_PAD = 12
const BOTTOM_PAD = 12
const RIGHT_PAD = 4

export interface AccuracyTrendChartProps {
  points: readonly PulseAccuracyPoint[]
}

export function AccuracyTrendChart({ points }: AccuracyTrendChartProps) {
  const [width, setWidth] = useState(0)
  const onLayout = useCallback((event: { nativeEvent: { layout: { width: number } } }) => {
    const next = Math.max(0, event.nativeEvent.layout.width)
    setWidth((previous) => (Math.abs(previous - next) < 1 ? previous : next))
  }, [])

  const geometry = useMemo(() => {
    if (width <= 0 || points.length === 0) return null
    const innerW = Math.max(1, width - RIGHT_PAD)
    const innerH = CHART_HEIGHT - TOP_PAD - BOTTOM_PAD
    const coords = points.map((point, index) => {
      const x = points.length === 1 ? innerW / 2 : (innerW * index) / (points.length - 1)
      const y = TOP_PAD + innerH * (1 - point.accuracy)
      return { x, y, point }
    })
    const line = coords.map(({ x, y }) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
    const area = coords.length > 0
      ? `${coords[0]!.x.toFixed(1)},${(CHART_HEIGHT - BOTTOM_PAD).toFixed(1)} ${line} ${coords[coords.length - 1]!.x.toFixed(1)},${(CHART_HEIGHT - BOTTOM_PAD).toFixed(1)}`
      : ''
    return { coords, line, area, innerW }
  }, [points, width])

  if (points.length === 0) {
    return (
      <View className="rounded-xl border border-wood-600/40 bg-wood-900/35 px-5 py-6">
        <Text className="font-serif text-lg text-cream">No scored sessions yet</Text>
        <Text className="mt-1 font-sans text-sm leading-5 text-muted-light">
          Finish a session through Review to start your accuracy trend. The chart keeps the last ten
          scored sessions.
        </Text>
      </View>
    )
  }

  const delta = points.length >= 2 ? points[points.length - 1]!.accuracy - points[0]!.accuracy : null
  const deltaLabel =
    delta == null
      ? 'Complete one more session for a trend'
      : `${delta >= 0 ? '+' : ''}${Math.round(delta * 100)} pts across ${points.length} sessions`

  return (
    <View>
      <View className="mb-3 flex-row items-end justify-between gap-3">
        <View>
          <Text className="font-sans text-xs uppercase tracking-wider text-muted-light">
            Session accuracy
          </Text>
          <Text className="mt-1 font-serif text-2xl text-cream">
            {Math.round(points[points.length - 1]!.accuracy * 100)}%
          </Text>
        </View>
        <Text
          className={`pb-1 font-sans text-xs ${
            delta == null ? 'text-muted-light' : delta >= 0 ? 'text-success' : 'text-danger'
          }`}
        >
          {deltaLabel}
        </Text>
      </View>

      <View className="flex-row">
        <View className="mr-2 justify-between" style={{ height: CHART_HEIGHT, paddingTop: TOP_PAD - 5, paddingBottom: BOTTOM_PAD - 5 }}>
          <Text className="font-mono text-[9px] text-muted-light/70">100%</Text>
          <Text className="font-mono text-[9px] text-muted-light/70">50%</Text>
          <Text className="font-mono text-[9px] text-muted-light/70">0%</Text>
        </View>
        <View className="flex-1" onLayout={onLayout}>
          {width > 0 && geometry ? (
            <Svg width={width} height={CHART_HEIGHT}>
              <Defs>
                <SvgLinearGradient id="pulseAccuracyFill" x1="0" y1="0" x2="0" y2="1">
                  <Stop offset="0" stopColor={colors.amber.accent} stopOpacity={0.28} />
                  <Stop offset="1" stopColor={colors.amber.accent} stopOpacity={0} />
                </SvgLinearGradient>
              </Defs>

              {[0, 0.5, 1].map((value) => {
                const y = TOP_PAD + (CHART_HEIGHT - TOP_PAD - BOTTOM_PAD) * (1 - value)
                return (
                  <Line
                    key={`grid-${value}`}
                    x1={0}
                    y1={y}
                    x2={geometry.innerW}
                    y2={y}
                    stroke={colors.wood[600]}
                    strokeOpacity={0.45}
                    strokeWidth={1}
                    strokeDasharray={value === 0 ? undefined : '3 5'}
                  />
                )
              })}

              {points.length >= 2 ? (
                <>
                  <Polygon points={geometry.area} fill="url(#pulseAccuracyFill)" />
                  <Polyline
                    points={geometry.line}
                    fill="none"
                    stroke={colors.amber.accent}
                    strokeWidth={2.5}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </>
              ) : null}

              {geometry.coords.map(({ x, y, point }) => (
                <Circle
                  key={point.id}
                  cx={x}
                  cy={y}
                  r={4}
                  fill={colors.wood[900]}
                  stroke={colors.amber.light}
                  strokeWidth={2}
                />
              ))}
            </Svg>
          ) : null}
        </View>
      </View>

      <View className="ml-8 mt-1 flex-row justify-between">
        <Text className="font-sans text-[10px] text-muted-light/75">{points[0]!.label}</Text>
        <Text className="font-sans text-[10px] text-muted-light/60">
          {points.length} session{points.length === 1 ? '' : 's'}
        </Text>
        <Text className="font-sans text-[10px] text-muted-light/75">
          {points[points.length - 1]!.label}
        </Text>
      </View>
    </View>
  )
}

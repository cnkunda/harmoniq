import { View } from 'react-native'
import Svg, { Circle, G, Line, Polygon, Text as SvgText } from 'react-native-svg'

import colors from '@/src/constants/colors'

type GraphNode = {
  id: string
  label: string
  score: number
}

export interface SkillGraphProps {
  nodes?: GraphNode[]
  size?: number
}

const DEFAULT_NODES: GraphNode[] = [
  { id: 'timing', label: 'Timing', score: 0.62 },
  { id: 'pitch', label: 'Pitch', score: 0.74 },
  { id: 'phrasing', label: 'Phrasing', score: 0.58 },
  { id: 'dynamics', label: 'Dynamics', score: 0.46 },
  { id: 'tone', label: 'Tone', score: 0.67 },
]

export function SkillGraph({ nodes = DEFAULT_NODES, size = 240 }: SkillGraphProps) {
  const safeNodes = nodes.length >= 3 ? nodes : DEFAULT_NODES
  const center = size / 2
  const radius = Math.min(90, size * 0.35)
  const levels = 4
  const total = safeNodes.length

  const angleOf = (index: number) => (index * 2 * Math.PI) / total - Math.PI / 2
  const pointAt = (angle: number, pointRadius: number) => ({
    x: center + pointRadius * Math.cos(angle),
    y: center + pointRadius * Math.sin(angle),
  })

  const clampScore = (score: number) => Math.max(0, Math.min(1, Number.isFinite(score) ? score : 0))

  const gridPolygons = Array.from({ length: levels }, (_, levelIndex) => {
    const ringRadius = (radius / levels) * (levelIndex + 1)
    return safeNodes
      .map((_, nodeIndex) => {
        const point = pointAt(angleOf(nodeIndex), ringRadius)
        return `${point.x},${point.y}`
      })
      .join(' ')
  })

  const dataPolygon = safeNodes
    .map((node, nodeIndex) => {
      const point = pointAt(angleOf(nodeIndex), clampScore(node.score) * radius)
      return `${point.x},${point.y}`
    })
    .join(' ')

  return (
    <View className="w-full items-center rounded-2xl border border-wood-700/50 bg-wood-800/40 p-4">
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {gridPolygons.map((points, index) => (
          <Polygon key={`ring-${index}`} points={points} fill="none" stroke={colors.wood[600]} strokeWidth={1} />
        ))}

        {safeNodes.map((node, index) => {
          const angle = angleOf(index)
          const axisEnd = pointAt(angle, radius)
          const labelPoint = pointAt(angle, radius + 18)
          return (
            <G key={node.id}>
              <Line x1={center} y1={center} x2={axisEnd.x} y2={axisEnd.y} stroke={colors.wood[600]} strokeWidth={1} />
              <SvgText
                x={labelPoint.x}
                y={labelPoint.y + 4}
                fill={colors.muted.light}
                fontSize={10}
                textAnchor="middle"
                fontFamily="DMSans-Regular"
              >
                {node.label}
              </SvgText>
            </G>
          )
        })}

        <Polygon points={dataPolygon} fill={colors.amber.accent} fillOpacity={0.2} stroke={colors.amber.accent} strokeWidth={2} />

        {safeNodes.map((node, index) => {
          const point = pointAt(angleOf(index), clampScore(node.score) * radius)
          return <Circle key={`dot-${node.id}`} cx={point.x} cy={point.y} r={3.5} fill={colors.amber.accent} />
        })}
      </Svg>
    </View>
  )
}

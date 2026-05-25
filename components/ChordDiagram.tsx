import { useMemo } from 'react'
import { Text, View } from 'react-native'
import { Circle, Line, Svg } from 'react-native-svg'

import colors from '@/src/constants/colors'
import { chordToFretboardCells, formatChordDisplay } from '@/src/music/chordVoicing'

const FRET_COUNT = 4
const STRING_COUNT = 6

type Size = 'sm' | 'md' | 'lg'

const SIZE_CONFIG: Record<Size, { cellW: number; cellH: number; padX: number; padY: number; dotR: number; labelSize: number }> = {
  sm: { cellW: 18, cellH: 14, padX: 8, padY: 6, dotR: 3.5, labelSize: 9 },
  md: { cellW: 24, cellH: 18, padX: 10, padY: 8, dotR: 4.5, labelSize: 10 },
  lg: { cellW: 30, cellH: 22, padX: 12, padY: 10, dotR: 5.5, labelSize: 11 },
}

interface ChordDiagramProps {
  name: string
  size?: Size
  isActive?: boolean
}

export function ChordDiagram({ name, size = 'md', isActive = false }: ChordDiagramProps) {
  const cfg = SIZE_CONFIG[size]

  const svgW = cfg.padX * 2 + cfg.cellW * (FRET_COUNT + 1)
  const svgH = cfg.padY * 2 + cfg.cellH * (STRING_COUNT - 1)

  const cells = useMemo(() => {
    if (!name) return []
    return chordToFretboardCells(name, 'compact', 'open')
  }, [name])

  const noteDots = useMemo(() => {
    return cells.map((cell) => {
      const row = cell.string - 1
      const x = cell.fret === 0
        ? cfg.padX - cfg.cellW / 2
        : cfg.padX + (cell.fret - 1) * cfg.cellW + cfg.cellW / 2
      const y = cfg.padY + row * cfg.cellH
      return { x, y, fret: cell.fret, interval: cell.interval }
    })
  }, [cells, cfg])

  const displayName = formatChordDisplay(name)

  return (
    <View className="items-center" accessibilityLabel={`Chord diagram: ${displayName}`} accessible>
      <Svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        {/* Strings */}
        {Array.from({ length: STRING_COUNT }).map((_, si) => (
          <Line
            key={`s${si}`}
            x1={cfg.padX}
            y1={cfg.padY + si * cfg.cellH}
            x2={cfg.padX + cfg.cellW * (FRET_COUNT + 1)}
            y2={cfg.padY + si * cfg.cellH}
            stroke={colors.wood[500]}
            strokeWidth={si === 0 ? 2 : 1}
            strokeLinecap="round"
          />
        ))}
        {/* Frets */}
        {Array.from({ length: FRET_COUNT + 2 }).map((_, fi) => (
          <Line
            key={`f${fi}`}
            x1={cfg.padX + fi * cfg.cellW}
            y1={cfg.padY}
            x2={cfg.padX + fi * cfg.cellW}
            y2={cfg.padY + cfg.cellH * (STRING_COUNT - 1)}
            stroke={fi === 0 ? colors.cream : colors.wood[600]}
            strokeWidth={fi === 0 ? 2.5 : fi === FRET_COUNT + 1 ? 2.5 : 0.8}
            strokeLinecap="round"
          />
        ))}
        {/* Note dots */}
        {noteDots.map((dot, i) => (
          <Circle
            key={i}
            cx={dot.x}
            cy={dot.y}
            r={dot.fret === 0 ? cfg.dotR - 0.5 : cfg.dotR}
            fill={dot.fret === 0 ? 'none' : (dot.interval === 0 ? colors.amber.accent : `${colors.amber.accent}80`)}
            stroke={colors.amber.accent}
            strokeWidth={dot.fret === 0 ? 1.5 : 0.8}
          />
        ))}
      </Svg>
      <Text
        className={`mt-1 font-mono ${isActive ? 'text-amber-accent' : 'text-muted-brown'}`}
        style={{ fontSize: cfg.labelSize }}
      >
        {displayName}
      </Text>
    </View>
  )
}

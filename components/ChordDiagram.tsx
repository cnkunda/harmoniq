import { useMemo } from 'react'
import { Text, View } from 'react-native'
import { Circle, Line, Svg, Text as SvgText } from 'react-native-svg'

import { colors } from '@/src/constants/colors'
import {
  type ChordDbPosition,
  getChordPositionAtIndex,
} from '@/src/music/chordDbAdapter'
import {
  chordToFretboardCells,
  formatChordDisplay,
  noteToPitchClass,
  parseChordSymbol,
} from '@/src/music/chordVoicing'

type Size = 'sm' | 'md' | 'lg'

const STRING_COUNT = 6
const FRET_COUNT = 4

const SIZE_CONFIG: Record<Size, {
  cellW: number; cellH: number; padX: number; padY: number; dotR: number
  labelSize: number; fingerSize: number; markerSize: number
}> = {
  sm: { cellW: 14, cellH: 12, padX: 8, padY: 8, dotR: 3.5, labelSize: 9, fingerSize: 5, markerSize: 5 },
  md: { cellW: 18, cellH: 15, padX: 10, padY: 10, dotR: 4.5, labelSize: 10, fingerSize: 6, markerSize: 6 },
  lg: { cellW: 22, cellH: 18, padX: 12, padY: 12, dotR: 5.5, labelSize: 11, fingerSize: 7, markerSize: 7 },
}

interface ChordDiagramProps {
  name: string
  size?: Size
  isActive?: boolean
  positionIndex?: number
  showFingerNumbers?: boolean
  showChordName?: boolean
}

interface Dot {
  x: number
  y: number
  isOpen: boolean
  isMuted: boolean
  finger: number
  actualFret: number
  barreTop: boolean
  barreBottom: boolean
  isRoot: boolean
}

interface BarreInfo {
  fret: number
  yTop: number
  yBottom: number
}

function buildDotsFromChordsDb(
  position: ChordDbPosition,
  cfg: ReturnType<typeof getSizeConfig>,
  rootPc: number,
): { dots: Dot[]; barres: BarreInfo[] } {
  const revFrets = [...position.frets].reverse()
  const revFingers = [...position.fingers].reverse()
  const revMidi = position.midi ? [...position.midi].reverse() : []

  const dots: Dot[] = []
  const barres: BarreInfo[] = []
  const barreFrets = new Set(position.barres)

  let minBarreY = Infinity
  let maxBarreY = -Infinity

  for (let si = 0; si < STRING_COUNT; si++) {
    const f = revFrets[si]!
    const finger = revFingers[si]!

    if (f === -1) {
      dots.push({
        x: cfg.padX + si * cfg.cellW,
        y: cfg.padY - cfg.cellH * 0.3,
        isOpen: false,
        isMuted: true,
        finger: 0,
        actualFret: -1,
        barreTop: false,
        barreBottom: false,
        isRoot: false,
      })
      continue
    }

    if (f === 0) {
      const midi = revMidi[si]
      const pc = midi != null ? ((Math.round(midi) % 12) + 12) % 12 : -1
      dots.push({
        x: cfg.padX + si * cfg.cellW,
        y: cfg.padY - cfg.cellH * 0.3,
        isOpen: true,
        isMuted: false,
        finger: 0,
        actualFret: 0,
        barreTop: false,
        barreBottom: false,
        isRoot: pc === rootPc,
      })
      continue
    }

    const isBarred = barreFrets.has(f)
    const dotY = cfg.padY + (f - 1) * cfg.cellH + cfg.cellH / 2

    const midi = revMidi[si]
    const pc = midi != null ? ((Math.round(midi) % 12) + 12) % 12 : -1

    dots.push({
      x: cfg.padX + si * cfg.cellW,
      y: dotY,
      isOpen: false,
      isMuted: false,
      finger,
      actualFret: position.baseFret + f - 1,
      barreTop: false,
      barreBottom: false,
      isRoot: pc === rootPc,
    })

    if (isBarred) {
      if (dotY < minBarreY) minBarreY = dotY
      if (dotY > maxBarreY) maxBarreY = dotY
    }
  }

  if (position.barres.length > 0 && minBarreY < Infinity) {
    barres.push({
      fret: position.barres[0]!,
      yTop: minBarreY - cfg.cellH * 0.3,
      yBottom: maxBarreY + cfg.cellH * 0.3,
    })
  }

  return { dots, barres }
}

function buildDotsFromAlgorithmic(
  name: string,
  cfg: ReturnType<typeof getSizeConfig>,
): { dots: Dot[]; barres: BarreInfo[] } {
  const cells = chordToFretboardCells(name, 'compact', 'open')
  const dots: Dot[] = []

  const stringPositions: Record<number, { fret: number; interval: number } | null> = {}
  for (let s = 1; s <= STRING_COUNT; s++) {
    stringPositions[s] = null
  }

  for (const cell of cells) {
    if (!stringPositions[cell.string]) {
      stringPositions[cell.string] = { fret: cell.fret, interval: cell.interval }
    }
  }

  const sortedStrings = [6, 5, 4, 3, 2, 1]
  for (let si = 0; si < sortedStrings.length; si++) {
    const s = sortedStrings[si]!
    const pos = stringPositions[s]

    if (!pos || pos.fret === -1) {
      dots.push({
        x: cfg.padX + si * cfg.cellW,
        y: cfg.padY - cfg.cellH * 0.3,
        isOpen: false, isMuted: true,
        finger: 0, actualFret: -1,
        barreTop: false, barreBottom: false,
        isRoot: false,
      })
      continue
    }

    if (pos.fret === 0) {
      dots.push({
        x: cfg.padX + si * cfg.cellW,
        y: cfg.padY - cfg.cellH * 0.3,
        isOpen: true, isMuted: false,
        finger: 0, actualFret: 0,
        barreTop: false, barreBottom: false,
        isRoot: pos.interval === 0,
      })
      continue
    }

    const f = Math.max(1, pos.fret)
    dots.push({
      x: cfg.padX + si * cfg.cellW,
      y: cfg.padY + (f - 1) * cfg.cellH + cfg.cellH / 2,
      isOpen: false, isMuted: false,
      finger: 0, actualFret: f,
      barreTop: false, barreBottom: false,
      isRoot: pos.interval === 0,
    })
  }

  return { dots, barres: [] }
}

function getSizeConfig(size: Size) {
  return SIZE_CONFIG[size]
}

export function ChordDiagram({
  name,
  size = 'md',
  isActive = false,
  positionIndex = 0,
  showFingerNumbers = true,
  showChordName = true,
}: ChordDiagramProps) {
  const cfg = getSizeConfig(size)

  const svgW = cfg.padX * 2 + cfg.cellW * (STRING_COUNT - 1)
  const svgH = cfg.padY * 2 + cfg.cellH * FRET_COUNT + cfg.cellH * 0.5

  const rootPc = useMemo(() => {
    if (!name || name === 'N') return -1
    const parsed = parseChordSymbol(name)
    return parsed ? noteToPitchClass(parsed.root) : -1
  }, [name])

  const { dots, barres, baseFret } = useMemo(() => {
    if (!name || name === 'N') return { dots: [] as Dot[], barres: [] as BarreInfo[], baseFret: 1 }

    const pos = getChordPositionAtIndex(name, positionIndex)
    if (pos) {
      return { ...buildDotsFromChordsDb(pos, cfg, rootPc), baseFret: pos.baseFret }
    }

    return { ...buildDotsFromAlgorithmic(name, cfg), baseFret: 1 }
  }, [name, positionIndex, cfg, rootPc])

  const displayName = formatChordDisplay(name)

  return (
    <View
      testID="chord-diagram"
      className="items-center"
      accessibilityLabel={`Chord diagram: ${displayName}`}
      accessible
    >
      <Svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        {/* Strings (vertical lines) */}
        {Array.from({ length: STRING_COUNT }).map((_, si) => (
          <Line
            key={`s${si}`}
            x1={cfg.padX + si * cfg.cellW}
            y1={cfg.padY}
            x2={cfg.padX + si * cfg.cellW}
            y2={cfg.padY + FRET_COUNT * cfg.cellH}
            stroke={colors.wood[500]}
            strokeWidth={0.8}
            strokeLinecap="round"
          />
        ))}

        {/* Frets (horizontal lines) */}
        {Array.from({ length: FRET_COUNT + 1 }).map((_, fi) => (
          <Line
            key={`f${fi}`}
            x1={cfg.padX}
            y1={cfg.padY + fi * cfg.cellH}
            x2={cfg.padX + (STRING_COUNT - 1) * cfg.cellW}
            y2={cfg.padY + fi * cfg.cellH}
            stroke={fi === 0 ? colors.cream : colors.wood[600]}
            strokeWidth={fi === 0 ? 2.5 : 0.8}
            strokeLinecap="round"
          />
        ))}

        {/* Base fret label */}
        {baseFret > 1 && (
          <SvgText
            x={cfg.padX - cfg.cellW * 0.15}
            y={cfg.padY + cfg.cellH * 1.2}
            fontSize={cfg.markerSize}
            fill={colors.wood[500]}
            textAnchor="end"
          >
            {baseFret === 1 ? '' : ` ${String.fromCharCode(8543 + baseFret)}`}
          </SvgText>
        )}

        {/* Barre */}
        {barres.map((b, i) => (
          <Line
            key={`barre-${i}`}
            x1={cfg.padX - cfg.cellW * 0.15}
            y1={(b.yTop + b.yBottom) / 2}
            x2={cfg.padX + (STRING_COUNT - 1) * cfg.cellW + cfg.cellW * 0.15}
            y2={(b.yTop + b.yBottom) / 2}
            stroke={colors.cream}
            strokeWidth={3}
            strokeLinecap="round"
            opacity={0.7}
          />
        ))}

        {/* Dots */}
        {dots.map((dot, i) => {
          if (dot.isMuted) {
            return (
              <ReactMuteX key={`d${i}`} x={dot.x} y={dot.y} size={cfg.markerSize} />
            )
          }
          if (dot.isOpen) {
            return (
              <ReactOpenO key={`d${i}`} x={dot.x} y={dot.y} r={cfg.dotR} />
            )
          }
          return (
            <ReactFilledDot
              key={`d${i}`}
              x={dot.x}
              y={dot.y}
              r={cfg.dotR}
              finger={showFingerNumbers && dot.finger > 0 ? dot.finger : 0}
              fingerSize={cfg.fingerSize}
              isRoot={dot.isRoot}
            />
          )
        })}
      </Svg>

      {showChordName && (
        <Text
          className={`mt-1 font-mono ${isActive ? 'text-amber-accent' : 'text-muted-brown'}`}
          style={{ fontSize: cfg.labelSize }}
        >
          {displayName}
        </Text>
      )}
    </View>
  )
}

function ReactMuteX({ x, y, size }: { x: number; y: number; size: number }) {
  const half = size / 2
  return (
    <>
      <Line x1={x - half} y1={y - half} x2={x + half} y2={y + half} stroke={colors.wood[500]} strokeWidth={1.2} />
      <Line x1={x - half} y1={y + half} x2={x + half} y2={y - half} stroke={colors.wood[500]} strokeWidth={1.2} />
    </>
  )
}

function ReactOpenO({ x, y, r }: { x: number; y: number; r: number }) {
  return (
    <Circle
      cx={x}
      cy={y}
      r={r}
      fill="none"
      stroke={colors.amber.accent}
      strokeWidth={1.2}
    />
  )
}

function ReactFilledDot({
  x, y, r, finger, fingerSize, isRoot,
}: {
  x: number; y: number; r: number; finger: number; fingerSize: number; isRoot: boolean
}) {
  return (
    <>
      <Circle
        cx={x}
        cy={y}
        r={r}
        fill={isRoot ? colors.amber.accent : `${colors.amber.accent}80`}
      />
      {finger > 0 && (
        <SvgText
          x={x}
          y={y + fingerSize * 0.35}
          fontSize={fingerSize}
          fill={colors.wood[900]}
          textAnchor="middle"
          fontWeight="bold"
        >
          {finger}
        </SvgText>
      )}
    </>
  )
}

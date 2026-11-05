import { useMemo } from 'react'
import { Text, View } from 'react-native'

import { colors } from '@/src/constants/colors'
import {
  CHORD_QUALITY_COLUMNS,
  PULSE_ROOTS,
  type ChordMasteryCell,
  type ChordMasteryHeatmap as ChordMasteryHeatmapData,
} from '@/src/progress/pulseData'

// Discrete palette steps (danger → amber → success) instead of runtime color
// mixing: interpolated hexes are off-palette and fail the design-token check.
function masteryColor(mastery: number | null): string {
  if (mastery == null) return `${colors.wood[700]}66`
  if (mastery < 0.25) return colors.danger
  if (mastery < 0.5) return colors.amber.accent
  if (mastery < 0.75) return colors.amber.light
  return colors.success
}

export interface ChordMasteryHeatmapProps {
  heatmap: ChordMasteryHeatmapData
}

export function ChordMasteryHeatmap({ heatmap }: ChordMasteryHeatmapProps) {
  const byKey = useMemo(() => {
    const map = new Map<string, ChordMasteryCell>()
    for (const cell of heatmap.cells) map.set(`${cell.rootPc}:${cell.quality}`, cell)
    return map
  }, [heatmap.cells])

  const correctionTotal = heatmap.cells.reduce((sum, cell) => sum + cell.correctionCount, 0)
  const practiceTotal = heatmap.cells.reduce((sum, cell) => sum + cell.practiceCount, 0)

  return (
    <View>
      <View className="mb-3 flex-row items-baseline justify-between">
        <Text className="font-sans text-xs uppercase tracking-wider text-muted-light">
          Chord mastery
        </Text>
        <Text className="font-sans text-[10px] text-muted-light/85">
          {practiceTotal} chord passes · {correctionTotal} correction{correctionTotal === 1 ? '' : 's'}
        </Text>
      </View>

      {heatmap.populatedCount === 0 ? (
        <Text className="mb-3 font-sans text-xs leading-5 text-muted-light">
          No mastery estimate yet. Finish a scored session or correct a chord to light up the grid.
        </Text>
      ) : null}

      <View className="gap-1">
        <View className="flex-row items-center gap-1">
          <View className="w-7" />
          {CHORD_QUALITY_COLUMNS.map((column) => (
            <View key={column.id} className="flex-1 items-center">
              <Text className="font-mono text-[9px] text-muted-light/75">{column.label}</Text>
            </View>
          ))}
        </View>

        {PULSE_ROOTS.map((rootLabel, rootPc) => (
          <View key={rootLabel} className="flex-row items-center gap-1">
            <Text className="w-7 font-mono text-[10px] text-muted-light/80">{rootLabel}</Text>
            {CHORD_QUALITY_COLUMNS.map((column) => {
              const cell = byKey.get(`${rootPc}:${column.id}`)
              const mastery = cell?.mastery ?? null
              const percentage = mastery == null ? null : Math.round(mastery * 100)
              return (
                <View
                  key={`${rootLabel}-${column.id}`}
                  accessible
                  accessibilityRole="text"
                  accessibilityLabel={
                    cell == null
                      ? `${rootLabel} ${column.label}, no data`
                      : `${rootLabel} ${column.label}, ${percentage ?? 'no'} estimated mastery, ${cell.practiceCount} chord passes, ${cell.correctionCount} corrections`
                  }
                  className="h-5 flex-1 rounded-[3px]"
                  style={{
                    backgroundColor: masteryColor(mastery),
                    borderWidth: mastery == null ? 1 : 0,
                    borderColor: `${colors.wood[600]}55`,
                  }}
                />
              )
            })}
          </View>
        ))}
      </View>

      <View className="mt-3 flex-row items-center justify-between">
        <View className="flex-row items-center gap-1.5">
          <Text className="font-sans text-[10px] text-muted-light/85">Less</Text>
          {[0.1, 0.3, 0.5, 0.7, 0.9].map((value) => (
            <View
              key={value}
              className="h-3 w-4 rounded-[2px]"
              style={{ backgroundColor: masteryColor(value) }}
            />
          ))}
          <Text className="font-sans text-[10px] text-muted-light/85">More</Text>
        </View>
        <Text className="font-sans text-[10px] text-muted-light/85">
          {heatmap.sessionCount} session{heatmap.sessionCount === 1 ? '' : 's'} sampled
        </Text>
      </View>

      <Text className="mt-3 font-sans text-[10px] leading-4 text-muted-light/85">
        Estimated from session accuracy on songs that contain each chord, then reduced by chord
        corrections. Not a note-by-note hit rate.
      </Text>
    </View>
  )
}

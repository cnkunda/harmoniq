import React, { useCallback } from 'react'
import { View, Text, FlatList } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'
import type { CorrectionRecord } from '@/src/types'

export type CorrectionHistoryItem = CorrectionRecord

export interface CorrectionHistoryPanelProps {
  corrections: CorrectionHistoryItem[]
  correctionCount: number
  correctionCoverage: number
  onRevert: (correctionIndex: number) => void
  style?: object
}

function formatCorrectionSummary(item: CorrectionHistoryItem): string {
  switch (item.correction_type) {
    case 'chord': {
      const original = item.original_value.chord as string
      const corrected = item.corrected_value.chord as string
      return `${original} → ${corrected}`
    }
    case 'solo_note': {
      const changes = Object.keys(item.corrected_value).filter((k) => k !== 'reason')
      return `Note ${item.index}: ${changes.join(', ')}`
    }
    case 'voicing': {
      const shape = item.corrected_value.voicing_shape as string
      return `Voicing: ${shape}`
    }
    default:
      return `Correction #${item.index}`
  }
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export function CorrectionHistoryPanel({
  corrections,
  correctionCount,
  correctionCoverage,
  onRevert,
  style,
}: CorrectionHistoryPanelProps) {
  return (
    <View
      style={[
        {
          backgroundColor: colors.wood[800],
          borderWidth: 1,
          borderColor: colors.wood[600],
          borderRadius: 12,
          padding: 12,
        },
        style,
      ]}
    >
      <View className="flex-row items-center justify-between mb-3">
        <Text className="text-sm font-serif" style={{ color: colors.cream }}>
          Corrections
        </Text>
        <View className="flex-row items-center gap-2">
          <Text className="text-xs font-sans" style={{ color: colors.muted.light }}>
            {correctionCount} ({Math.round(correctionCoverage * 100)}% coverage)
          </Text>
        </View>
      </View>

      {corrections.length === 0 ? (
        <Text className="text-xs font-sans py-2" style={{ color: colors.muted.light }}>
          No corrections yet
        </Text>
      ) : (
        <FlatList
          data={corrections}
          keyExtractor={(_, i) => String(i)}
          renderItem={({ item, index }) => (
            <View
              className="flex-row items-center justify-between py-2 border-b"
              style={{ borderColor: colors.wood[600] }}
            >
              <View className="flex-1">
                <View className="flex-row items-center gap-2">
                  <View
                    className="rounded-full px-2 py-0.5"
                    style={{
                      backgroundColor:
                        item.correction_type === 'chord'
                          ? colors.wood[600]
                          : item.correction_type === 'solo_note'
                            ? colors.amber.accent
                            : colors.success,
                    }}
                  >
                    <Text
                      className="text-xs font-sans"
                      style={{
                        color:
                          item.correction_type === 'voicing'
                            ? colors.wood[900]
                            : colors.cream,
                      }}
                    >
                      {item.correction_type}
                    </Text>
                  </View>
                  <Text className="text-xs font-mono" style={{ color: colors.cream }}>
                    {formatCorrectionSummary(item)}
                  </Text>
                </View>
                {item.reason ? (
                  <Text className="text-xs font-sans mt-1" style={{ color: colors.muted.light }}>
                    {item.reason}
                  </Text>
                ) : null}
                <Text className="text-xs font-sans mt-0.5" style={{ color: colors.muted.light }}>
                  {formatTimestamp(item.applied_at)}
                </Text>
              </View>
              <AnimatedPressable
                onPress={() => onRevert(index)}
                haptic="light"
                className="rounded-md px-2 py-1 ml-2"
                style={{ backgroundColor: colors.danger }}
              >
                <Text className="text-xs font-sans" style={{ color: colors.cream }}>
                  Revert
                </Text>
              </AnimatedPressable>
            </View>
          )}
          style={{ maxHeight: 200 }}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  )
}

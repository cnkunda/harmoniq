import { Text, View } from 'react-native'

import type { ScoreResult } from '@/src/types'

/** Placeholder phrasing strip — shared by live Review and archived replay (PRIORITIES §35). */
export function PhrasingVisualizerStub() {
  return (
    <View className="mt-3 rounded-lg border border-wood-600/45 bg-cream-dark/40 px-3 py-3">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
        Phrasing visualizer (stub)
      </Text>
      <View className="mt-2 h-28 w-full overflow-hidden rounded-md border border-wood-600/45 bg-ivory">
        <View className="absolute inset-0 flex-row">
          {Array.from({ length: 12 }, (_, i) => (
            <View key={`grid-${i}`} className="h-full flex-1 border-r border-wood-600/20" />
          ))}
        </View>
        <View className="absolute left-2 right-2 top-6 h-1 rounded-full bg-danger/70" />
        <View className="absolute left-2 right-4 top-14 h-1 rounded-full bg-amber-accent/85" />
        <View className="absolute left-4 right-10 top-22 h-1 rounded-full bg-danger/70" />
      </View>
      <Text className="mt-2 font-sans text-[11px] text-muted-light">
        Terracotta = your take, amber = reference guide. Beat lines are static until the live phrasing overlay is wired up.
      </Text>
    </View>
  )
}

export function ScoreSummaryCard({ score }: { score: ScoreResult }) {
  return (
    <View className="mt-3 rounded-lg border border-success/30 bg-success/10 px-3 py-3">
      <Text className="font-sans-medium text-sm text-wood-900">Score summary</Text>
      <Text className="mt-1 font-sans text-xs text-muted-light">
        Percentages are 0–100 for pitch, phrasing, and timing; bend error is mean cents off target.
      </Text>
      <View className="mt-3 gap-2 border-t border-success/20 pt-3">
        <Text className="font-sans text-sm text-wood-900">
          <Text className="font-sans-medium">Pitch accuracy</Text>
          {' · '}
          {(score.pitch_accuracy * 100).toFixed(0)}%
          <Text className="font-mono text-[11px] text-muted-light"> ({score.pitch_accuracy.toFixed(3)})</Text>
        </Text>
        <Text className="font-sans text-sm text-wood-900">
          <Text className="font-sans-medium">Phrasing</Text>
          {' · '}
          {(score.phrasing_score * 100).toFixed(0)}%
          <Text className="font-mono text-[11px] text-muted-light"> ({score.phrasing_score.toFixed(3)})</Text>
        </Text>
        <Text className="font-sans text-sm text-wood-900">
          <Text className="font-sans-medium">Timing</Text>
          {' · '}
          {(score.rushing_score * 100).toFixed(0)}%
          <Text className="font-mono text-[11px] text-muted-light"> ({score.rushing_score.toFixed(3)})</Text>
        </Text>
        <Text className="font-sans text-sm text-wood-900">
          <Text className="font-sans-medium">Bend error</Text>
          {' · '}
          {score.bend_pitch_error_cents.toFixed(1)}¢
        </Text>
      </View>
      <Text className="mt-3 font-mono text-[10px] leading-4 text-muted-light">
        Skill model (this session): pitch {score.node_scores.pitch_accuracy?.toFixed(3) ?? '—'} · phrasing{' '}
        {score.node_scores.phrasing?.toFixed(3) ?? '—'} · timing {score.node_scores.timing?.toFixed(3) ?? '—'}
      </Text>
    </View>
  )
}

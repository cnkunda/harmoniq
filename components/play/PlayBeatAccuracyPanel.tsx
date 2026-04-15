import { Text, View } from 'react-native'

import { NoteAccuracyBar } from '@/components/NoteAccuracyBar'
import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'

type PlayBeatAccuracyPanelProps = {
  beats: NoteResultLabel[]
  noteLabels: string[]
  maxVisible?: number
}

function countLabels(beats: NoteResultLabel[]) {
  let hit = 0
  let close = 0
  let miss = 0
  for (const b of beats) {
    if (b === 'hit' || b === 'vibrato') hit += 1
    else if (b === 'close') close += 1
    else if (b === 'miss') miss += 1
  }
  return { hit, close, miss }
}

/**
 * Beat strip + per-beat pitch-class letters + simple hit/close/miss counts.
 */
export function PlayBeatAccuracyPanel({ beats, noteLabels, maxVisible = 24 }: PlayBeatAccuracyPanelProps) {
  const sliceLabels =
    noteLabels.length > maxVisible ? noteLabels.slice(-maxVisible) : noteLabels
  const sliceBeats = beats.length > maxVisible ? beats.slice(-maxVisible) : beats
  const n = Math.min(sliceBeats.length, sliceLabels.length)
  const alignedLabels = sliceLabels.slice(-n)
  const { hit, close, miss } = countLabels(beats.filter((b) => b !== 'ignored'))
  const scored = beats.filter((b) => b !== 'ignored').length
  const pct = scored > 0 ? Math.round(((hit + close) / scored) * 100) : null

  return (
    <View className="rounded-xl border border-wood-600/40 bg-cream-dark/50 p-4">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Score · by beat</Text>
      <Text className="mt-1 font-sans text-xs text-muted-brown">
        Each bar is one beat closed while capture runs; the letter is the target pitch for that beat (tab may have
        advanced mid-measure).
      </Text>
      <View className="mb-2 mt-3 flex-row items-center justify-between">
        <Text className="font-sans text-[11px] text-wood-900">On-pitch rate</Text>
        {pct != null ? (
          <Text className="font-mono text-xs text-wood-900">{pct}%</Text>
        ) : (
          <Text className="font-mono text-xs text-muted-brown">—</Text>
        )}
      </View>
      <NoteAccuracyBar beats={beats} maxVisible={maxVisible} />
      {n > 0 ? (
        <View className="mt-1.5 flex-row gap-0.5">
          {alignedLabels.map((label, i) => (
            <View key={`lb-${i}-${label}`} className="min-w-[6px] flex-1 items-center">
              <Text className="font-mono text-[8px] text-muted-brown" numberOfLines={1}>
                {label}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
      <Text className="mt-2 font-sans text-[11px] text-muted-brown">
        Hits {hit} · Close {close} · Miss {miss}
        {scored > 0 ? ` · ${scored} scored beats` : ''}
      </Text>
    </View>
  )
}

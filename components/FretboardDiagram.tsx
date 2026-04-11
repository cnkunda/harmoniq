import { Text, View } from 'react-native'

type FretboardDiagramProps = {
  keyLabel: string
  positionLabel: string
  capoText: string
  selectedNote?: {
    string?: number
    fret?: number
    midi?: number
  } | null
  pulseKey?: number
}

/**
 * Minimal pedagogy stub for Study step (commit 24):
 * six strings, five frets, and a tiny marker pattern.
 */
export function FretboardDiagram({ keyLabel, positionLabel, capoText, selectedNote, pulseKey = 0 }: FretboardDiagramProps) {
  const selectedString = typeof selectedNote?.string === 'number' ? selectedNote.string : null
  const selectedFret = typeof selectedNote?.fret === 'number' ? selectedNote.fret : null
  return (
    <View className="mt-3 rounded-xl border border-wood-600/45 bg-cream-dark/45 p-3">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Position map</Text>
      <Text className="mt-1 font-sans text-xs text-wood-900">
        {keyLabel} · {positionLabel}
      </Text>
      <Text className="mt-0.5 font-sans text-[11px] text-muted-brown">{capoText}</Text>

      <View className="mt-3 gap-1.5">
        {Array.from({ length: 6 }).map((_, stringIdx) => (
          <View key={`s-${stringIdx}`} className="relative h-4 justify-center">
            <View className="h-[1px] bg-wood-600/55" />
            <View className="absolute left-0 right-0 flex-row justify-between px-2">
              {Array.from({ length: 5 }).map((__, fretIdx) => {
                const on = (stringIdx + fretIdx) % 3 === 0
                const selected =
                  selectedString != null &&
                  selectedFret != null &&
                  Math.max(0, Math.min(5, selectedString)) === stringIdx &&
                  Math.max(1, Math.min(5, selectedFret)) - 1 === fretIdx
                return (
                  <View
                    key={`m-${stringIdx}-${fretIdx}`}
                    className={`h-2.5 w-2.5 rounded-full ${
                      selected ? 'bg-amber-accent' : on ? 'bg-amber-accent/60' : 'bg-transparent'
                    }`}
                  />
                )
              })}
            </View>
          </View>
        ))}
      </View>
      <Text className="mt-2 font-mono text-[10px] text-muted-brown">
        frets: 1 2 3 4 5 {selectedString != null && selectedFret != null ? `| selected s${selectedString} f${selectedFret} #${pulseKey}` : ''}
      </Text>
    </View>
  )
}

import { Text, View } from 'react-native'

type FretboardDiagramProps = {
  keyLabel: string
  positionLabel: string
  capoText: string
}

/**
 * Minimal pedagogy stub for Study step (commit 24):
 * six strings, five frets, and a tiny marker pattern.
 */
export function FretboardDiagram({ keyLabel, positionLabel, capoText }: FretboardDiagramProps) {
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
                return (
                  <View
                    key={`m-${stringIdx}-${fretIdx}`}
                    className={`h-2.5 w-2.5 rounded-full ${on ? 'bg-amber-accent' : 'bg-transparent'}`}
                  />
                )
              })}
            </View>
          </View>
        ))}
      </View>
      <Text className="mt-2 font-mono text-[10px] text-muted-brown">frets: 1 2 3 4 5</Text>
    </View>
  )
}

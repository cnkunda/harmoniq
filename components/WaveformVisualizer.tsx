import { Text, View } from 'react-native'

export interface WaveformVisualizerProps {
  isPlaying?: boolean
  progress?: number
  highlightRegion?: [number, number]
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function WaveformVisualizer(_props: WaveformVisualizerProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">WaveformVisualizer</Text>
    </View>
  )
}

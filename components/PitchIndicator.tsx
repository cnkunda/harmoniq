import { Text, View } from 'react-native'

export interface PitchIndicatorProps {
  note?: string
  cents?: number
  isActive?: boolean
  targetMidi?: number
}

function midiToHz(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

export function PitchIndicator({ note, cents, isActive, targetMidi }: PitchIndicatorProps) {
  const hz = typeof targetMidi === 'number' && Number.isFinite(targetMidi) ? midiToHz(targetMidi) : null
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">PitchIndicator</Text>
      <Text className="mt-1 font-sans text-xs text-muted-brown">
        target: {hz != null ? `${hz.toFixed(1)} Hz` : '—'} {note ? `| note: ${note}` : ''}{' '}
        {typeof cents === 'number' ? `| cents: ${Math.round(cents)}` : ''} {isActive ? '| active' : ''}
      </Text>
      <View className="mt-2 h-1.5 rounded-full bg-wood-600/40">
        <View className="h-1.5 w-1/2 rounded-full bg-amber-accent/80" />
      </View>
    </View>
  )
}

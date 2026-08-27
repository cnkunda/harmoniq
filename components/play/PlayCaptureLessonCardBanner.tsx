import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'
import { AudioWaveform, Mic } from 'lucide-react-native'

export type PlayCaptureLessonCardBannerProps = {
  loading: boolean
  ready: boolean
  playing: boolean
  recording: boolean
}

function backingStatusLabel(loading: boolean, ready: boolean, playing: boolean): string {
  if (loading || !ready) return 'Loading'
  return playing ? 'Playing' : 'Paused'
}

/**
 * Two-row status strip for the Play session “play capture” card: stems mix vs mic capture.
 */
export function PlayCaptureLessonCardBanner({
  loading,
  ready,
  playing,
  recording,
}: PlayCaptureLessonCardBannerProps) {
  const backing = backingStatusLabel(loading, ready, playing)
  const mic = recording ? 'Recording' : 'Idle'

  return (
    <View
      className="mt-3 rounded-lg border border-wood-600/25 bg-wood-900/5 px-3 py-2.5"
      accessible
      accessibilityLabel={`Backing track ${backing}. Microphone ${mic}.`}
    >
      <View className="flex-row items-center gap-2.5">
        <AudioWaveform size={18} color={colors.amber.accent} strokeWidth={1.75} />
        <Text className="min-w-0 flex-1 font-sans-medium text-xs text-wood-900">Backing track</Text>
        <View
          className={`rounded-full border px-2 py-0.5 ${
            playing && ready && !loading
              ? 'border-amber-accent/50 bg-amber-accent/15'
              : 'border-wood-600/35 bg-cream-dark/40'
          }`}
        >
          <Text
            className={`font-mono text-[10px] font-medium ${
              playing && ready && !loading ? 'text-wood-900' : 'text-muted-light'
            }`}
          >
            {backing}
          </Text>
        </View>
      </View>

      <View className="my-2.5 h-px bg-wood-600/15" />

      <View className="flex-row items-center gap-2.5">
        <Mic size={18} color={recording ? colors.danger : colors.muted.light} strokeWidth={1.75} />
        <Text className="min-w-0 flex-1 font-sans-medium text-xs text-wood-900">Your guitar (mic)</Text>
        <View className="flex-row items-center gap-1.5">
          {recording ? (
            <View className="h-2 w-2 rounded-full bg-danger" accessibilityLabel="Recording indicator" />
          ) : null}
          <View
            className={`rounded-full border px-2 py-0.5 ${
              recording ? 'border-danger/40 bg-danger/10' : 'border-wood-600/35 bg-cream-dark/40'
            }`}
          >
            <Text
              className={`font-mono text-[10px] font-medium ${recording ? 'text-danger' : 'text-muted-light'}`}
            >
              {recording ? 'Recording' : 'Idle'}
            </Text>
          </View>
        </View>
      </View>
    </View>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import type { RecordedTake } from '@/src/audio/recordSession.types'
import colors from '@/src/constants/colors'
import type { PlayLessonCaptureContext } from './playLessonCaptureTypes'
import { AudioWaveform, Circle, Mic, Play, Square } from 'lucide-react-native'

function formatMmSs(totalMs: number): string {
  const s = Math.max(0, Math.floor(totalMs / 1000))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
}

function backingStatusLabel(loading: boolean, ready: boolean, playing: boolean): string {
  if (loading || !ready) return 'Loading'
  return playing ? 'Playing' : 'Ready'
}

function micStatusLabel(recording: boolean, status: string): string {
  if (recording) return 'Recording'
  if (status.startsWith('Capture error')) return 'Error'
  if (status.includes('Starting')) return 'Starting…'
  return 'Armed'
}

export type PlayCaptureCardProps = PlayLessonCaptureContext & {
  recording: boolean
  status: string
  take: RecordedTake | null
  autostopTriggered: boolean
  onToggleCapture: () => void
  /** From usePlayCapture; null when not capturing. */
  recordingWallClockStartedAtMs: number | null
}

/**
 * Play session: PLAY CAPTURE block (song, backing/mic rows, full-width CTA + elapsed timer).
 */
export function PlayCaptureCard({
  songTitle,
  sectionLine,
  loading,
  ready,
  playing,
  recording,
  status,
  take,
  autostopTriggered,
  onToggleCapture,
  recordingWallClockStartedAtMs,
}: PlayCaptureCardProps) {
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    if (!recording || recordingWallClockStartedAtMs == null) return
    const id = setInterval(() => setNowMs(Date.now()), 250)
    return () => clearInterval(id)
  }, [recording, recordingWallClockStartedAtMs])

  const elapsedMs = useMemo(() => {
    if (!recording || recordingWallClockStartedAtMs == null) return 0
    return nowMs - recordingWallClockStartedAtMs
  }, [recording, recordingWallClockStartedAtMs, nowMs])

  const backing = backingStatusLabel(loading, ready, playing)
  const mic = micStatusLabel(recording, status)

  const backingDot =
    loading || !ready ? colors.muted.light : playing ? colors.amber.accent : colors.success
  const micDot = recording ? colors.danger : status.startsWith('Capture error') ? colors.danger : colors.success

  const rowWrap =
    'flex-row items-center justify-between gap-2 rounded-lg border border-wood-600/35 bg-cream-dark/40 px-3 py-2'

  return (
    <View className="gap-3">
      <Text className="font-sans-medium text-[10px] uppercase tracking-[0.12em] text-amber-accent">
        PLAY CAPTURE
      </Text>
      <Text className="font-sans-medium text-sm leading-snug text-wood-900" numberOfLines={2}>
        {songTitle}
      </Text>
      <Text className="font-sans text-xs text-muted-light">{sectionLine}</Text>

      <View className={rowWrap}>
        <View className="min-w-0 flex-1 flex-row items-center gap-2">
          <AudioWaveform size={16} color={colors.amber.accent} strokeWidth={1.75} />
          <Text className="font-sans-medium text-xs text-wood-900">Backing track</Text>
        </View>
        <View className="flex-row items-center gap-1.5">
          <Circle size={8} fill={backingDot} color={backingDot} />
          <Text className="font-mono text-[11px] font-medium text-wood-900">{backing}</Text>
        </View>
      </View>

      <View className={rowWrap}>
        <View className="min-w-0 flex-1 flex-row items-center gap-2">
          <Mic size={16} color={recording ? colors.danger : colors.muted.light} strokeWidth={1.75} />
          <Text className="font-sans-medium text-xs text-wood-900">Your guitar (mic)</Text>
        </View>
        <View className="flex-row items-center gap-1.5">
          <Circle size={8} fill={micDot} color={micDot} />
          <Text
            className={`font-mono text-[11px] font-medium ${recording ? 'text-danger' : 'text-wood-900'}`}
          >
            {mic}
          </Text>
        </View>
      </View>

      <View className="flex-row items-center gap-3">
        <AnimatedPressable
          onPress={onToggleCapture}
          className="min-h-[44px] flex-1 flex-row items-center justify-center gap-2 rounded-xl bg-amber-accent px-4 py-3"
          accessibilityRole="button"
          accessibilityLabel={recording ? 'Finish capture' : 'Start capture'}
        >
          {recording ? (
            <Square color={colors.wood[900]} size={18} fill={colors.wood[900]} strokeWidth={0} />
          ) : (
            <Play color={colors.wood[900]} size={18} fill={colors.wood[900]} strokeWidth={0} />
          )}
          <Text className="font-sans-medium text-wood-900">
            {recording ? 'Finish capture' : 'Start capture'}
          </Text>
        </AnimatedPressable>
        <Text className="shrink-0 font-mono text-sm tabular-nums text-wood-900">
          {formatMmSs(elapsedMs)}
        </Text>
      </View>

      {autostopTriggered ? (
        <Text className="font-sans text-xs text-muted-light">Auto-end triggered after 5 seconds of silence.</Text>
      ) : null}
      {take ? (
        <Text className="font-sans text-xs text-wood-900">
          Recorded take: {(take.durationMs / 1000).toFixed(1)}s, {take.audioBytes.length} bytes ({take.mimeType})
        </Text>
      ) : null}
    </View>
  )
}

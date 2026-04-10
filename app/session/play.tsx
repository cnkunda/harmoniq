import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Platform, Pressable, Text, View } from 'react-native'

import { ErrorBanner } from '@/components/ErrorBanner'
import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { createSessionRecorder } from '@/src/audio/recordSession'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import type { RecordedTake } from '@/src/audio/recordSession.types'
import type { PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import type { MappedUiError } from '@/src/errors/mapErrorToUi'
import { mapMicPermissionDenied, toErrorBannerProps } from '@/src/errors/mapErrorToUi'
import { openHarmoniqAppSettings } from '@/src/errors/openHarmoniqAppSettings'

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const PITCH_COLORS = {
  amber: 'bg-amber-accent',
  sage: 'bg-success',
  terracotta: 'bg-danger',
} as const

function noteNameToClass(note: string | null | undefined): number | null {
  if (!note) return null
  const token = note.trim().toUpperCase()
  const root = token.replace(/[0-9]/g, '')
  const idx = NOTE_NAMES.indexOf(root)
  return idx >= 0 ? idx : null
}

function hzToMidiFloat(hz: number): number {
  return 69 + 12 * Math.log2(hz / 440)
}

export default function PlayScreen() {
  const router = useRouter()
  const initialMetronomeOn = useMetronomeDefaultOn()
  const lesson = useLessonStore((s) => s.lesson)
  const sectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[sectionIndex] as Record<string, unknown> | undefined
  const setLatestTake = useSessionPlayStore((s) => s.setLatestTake)
  const keyRoot = typeof lesson?.key === 'string' ? lesson.key.split(/\s+/)[0] : null
  const rootPc = noteNameToClass(keyRoot)

  const targetLadder = useMemo(() => {
    const basePc = rootPc ?? 9 // A as fallback
    return Array.from({ length: 12 }, (_, i) => {
      const pc = (basePc + i) % 12
      return {
        pc,
        label: NOTE_NAMES[pc],
        midi: 60 + pc,
      }
    })
  }, [rootPc])

  const { start, stop } = usePitchStream()
  const recorderRef = useRef(createSessionRecorder())
  const lastPitchAtRef = useRef<number>(0)
  const tickRef = useRef<PlaybackTickContext | null>(null)
  const [pitchRunning, setPitchRunning] = useState(false)
  const [recording, setRecording] = useState(false)
  const [take, setTake] = useState<RecordedTake | null>(null)
  const [status, setStatus] = useState('Idle')
  const [targetLabel, setTargetLabel] = useState(targetLadder[0]?.label ?? 'A')
  const [centsFromTarget, setCentsFromTarget] = useState<number | null>(null)
  const [micError, setMicError] = useState<MappedUiError | null>(null)
  const [autostopTriggered, setAutostopTriggered] = useState(false)

  const startCapture = useCallback(async () => {
    setStatus('Starting mic + recorder…')
    setMicError(null)
    await recorderRef.current.start()
    await start((reading) => {
      lastPitchAtRef.current = Date.now()
      const midi = hzToMidiFloat(reading.hz)
      let best = targetLadder[0]
      let bestCents = Number.POSITIVE_INFINITY
      for (const cand of targetLadder) {
        for (const octave of [-12, 0, 12]) {
          const targetMidi = cand.midi + octave
          const cents = (midi - targetMidi) * 100
          const abs = Math.abs(cents)
          if (abs < Math.abs(bestCents)) {
            bestCents = cents
            best = cand
          }
        }
      }
      setTargetLabel(best.label)
      setCentsFromTarget(bestCents)
    })
    setTake(null)
    setRecording(true)
    setPitchRunning(true)
    setStatus('Capturing performance')
  }, [start, targetLadder])

  const stopCapture = useCallback(async (reason: 'done' | 'silence') => {
    if (!recording && !pitchRunning) return
    const rec = await recorderRef.current.stop()
    await stop()
    setRecording(false)
    setPitchRunning(false)
    setTake(rec)
    setLatestTake(rec)
    setStatus(reason === 'silence' ? 'Auto-stopped after 5s silence' : 'Capture stopped')
  }, [pitchRunning, recording, setLatestTake, stop])

  useEffect(() => {
    return () => {
      void stop().catch(() => {})
      void recorderRef.current.stop().catch(() => {})
    }
  }, [stop])

  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => {
      const ctx = tickRef.current
      if (!ctx?.playing) return
      const last = lastPitchAtRef.current
      if (last <= 0) return
      if (Date.now() - last >= 5000) {
        setAutostopTriggered(true)
        void stopCapture('silence')
      }
    }, 250)
    return () => clearInterval(id)
  }, [recording, stopCapture])

  const pitchBandClass =
    centsFromTarget == null
      ? 'bg-wood-600'
      : Math.abs(centsFromTarget) <= 15
        ? PITCH_COLORS.sage
        : Math.abs(centsFromTarget) <= 50
          ? PITCH_COLORS.amber
          : PITCH_COLORS.terracotta

  return (
    <SessionStepScreen
      title="Play"
      subtitle="Play along with backing mix (guitar muted), live pitch ladder, and in-memory take capture."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Review"
      onNext={() => router.push(sessionHref('review'))}
    >
      {Platform.OS === 'web' ? (
        <View className="rounded-lg border border-amber-accent/30 bg-amber-accent/10 px-3 py-2">
          <Text className="font-sans text-xs text-wood-900">
            Web play tip: allow microphone permissions and use headphones to reduce bleed/feedback.
          </Text>
          <Text className="mt-1 font-sans text-[11px] text-muted-brown">
            Browser mic capture needs HTTPS or localhost.
          </Text>
        </View>
      ) : null}

      <View className="mt-3 rounded-lg border border-wood-600/45 bg-cream-dark/40 px-3 py-3">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Pitch ladder</Text>
        <Text className="mt-1 font-mono text-xs text-muted-brown">
          Target note: {targetLabel} {centsFromTarget != null ? `(${centsFromTarget >= 0 ? '+' : ''}${Math.round(centsFromTarget)}c)` : ''}
        </Text>
        <View className="mt-2 flex-row items-end gap-1">
          {targetLadder.map((n) => {
            const active = n.label === targetLabel
            return (
              <View key={n.label} className="items-center">
                <View className={`h-8 w-3 rounded-sm ${active ? pitchBandClass : 'bg-wood-600/40'}`} />
                <Text className={`mt-1 font-mono text-[9px] ${active ? 'text-wood-900' : 'text-muted-brown'}`}>{n.label}</Text>
              </View>
            )
          })}
        </View>
        <Text className="mt-2 font-sans text-[11px] text-muted-brown">
          Thresholds: amber {'<='} 50c, sage {'<='} 15c, terracotta {'>'} 50c.
        </Text>
      </View>

      <View className="mt-3 flex-row flex-wrap items-center gap-2">
        <Pressable
          onPress={() => {
            void (recording ? stopCapture('done') : startCapture()).catch((e) => {
              const message = e instanceof Error ? e.message : String(e)
              if (message === 'MIC_PERMISSION_DENIED') {
                setMicError(mapMicPermissionDenied(Platform.OS))
              }
              setStatus(message === 'MIC_PERMISSION_DENIED' ? 'Microphone access needed' : `Capture error: ${message}`)
            })
          }}
          className="rounded-lg bg-amber-accent/90 px-4 py-2"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">{recording ? 'Done' : 'Start play capture'}</Text>
        </Pressable>
        <Text className="font-mono text-[11px] text-muted-brown">{status}</Text>
      </View>
      {micError ? (
        <ErrorBanner
          className="mt-2"
          dismissible={false}
          {...toErrorBannerProps(micError, {
            onRetry: () => setMicError(null),
            onDismiss: () => setMicError(null),
            onOpenSettings: () => {
              void openHarmoniqAppSettings()
              setMicError(null)
            },
            onContinue: () => setMicError(null),
          })}
        />
      ) : null}
      {autostopTriggered ? (
        <Text className="mt-1 font-sans text-xs text-muted-brown">Auto-end triggered after 5 seconds of silence.</Text>
      ) : null}
      {take ? (
        <Text className="mt-1 font-sans text-xs text-wood-900">
          Recorded take: {(take.durationMs / 1000).toFixed(1)}s, {take.audioBytes.length} bytes ({take.mimeType})
        </Text>
      ) : null}

      <SessionStemAndTab
        showSkewDemoButton={false}
        initialMetronomeOn={initialMetronomeOn}
        initialStemMuteById={{ guitar: true, bass: false, drums: false, vocals: true, piano: true, other: true }}
        onPlaybackTick={(ctx) => {
          tickRef.current = ctx
        }}
      />
      {section ? (
        <Text className="mt-2 font-mono text-[10px] text-muted-brown">
          Section: {String(section.label ?? 'Section')} {lesson?.key ? `| Key: ${lesson.key}` : ''}
        </Text>
      ) : null}
    </SessionStepScreen>
  )
}

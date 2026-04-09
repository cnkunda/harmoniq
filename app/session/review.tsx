import { useRouter } from 'expo-router'
import { Buffer } from 'buffer'
import * as FileSystem from 'expo-file-system/legacy'
import * as Sharing from 'expo-sharing'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Platform, Pressable, Text, View } from 'react-native'
import * as WebBrowser from 'expo-web-browser'

import { SessionStepScreen } from '@/components/SessionStepScreen'
import { submitScore } from '@/src/api/analyze'
import { applyReviewSkillUpdates, getSessionCount, insertSessionRow } from '@/src/db/client'
import { useSkillStore } from '@/src/stores/skillStore'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionPlayStore } from '@/src/stores/sessionPlayStore'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { ScoreResult } from '@/src/types'

function bytesToBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString('base64')
}

function midiVarLen(value: number): number[] {
  let buffer = value & 0x7f
  const out: number[] = []
  while ((value >>= 7) > 0) {
    buffer <<= 8
    buffer |= (value & 0x7f) | 0x80
  }
  for (;;) {
    out.push(buffer & 0xff)
    if (buffer & 0x80) buffer >>= 8
    else break
  }
  return out
}

function buildFallbackMidiBase64(tempoBpm: number | null | undefined, key: string | null | undefined): string {
  const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const root = typeof key === 'string' ? key.split(/\s+/)[0].toUpperCase() : 'A'
  const idx = noteNames.indexOf(root)
  const rootPc = idx >= 0 ? idx : 9
  const rootMidi = 60 + rootPc
  const tpq = 480
  const qnUs = Math.max(240000, Math.min(1200000, Math.round(60000000 / Math.max(40, Math.min(220, tempoBpm ?? 90)))))
  const tempoBytes = [(qnUs >> 16) & 0xff, (qnUs >> 8) & 0xff, qnUs & 0xff]

  const track: number[] = []
  track.push(0x00, 0xff, 0x51, 0x03, ...tempoBytes) // tempo meta
  track.push(0x00, 0xc0, 0x18) // nylon guitar
  const pattern = [0, 2, 4, 5, 7, 9, 7, 5]
  for (const step of pattern) {
    const midi = rootMidi + step
    track.push(0x00, 0x90, midi, 92) // note on
    track.push(...midiVarLen(tpq), 0x80, midi, 0x00) // note off after quarter
  }
  track.push(0x00, 0xff, 0x2f, 0x00) // end track

  const header = [0x4d, 0x54, 0x68, 0x64, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00, 0x01, (tpq >> 8) & 0xff, tpq & 0xff]
  const trackLen = track.length
  const trackHeader = [
    0x4d,
    0x54,
    0x72,
    0x6b,
    (trackLen >> 24) & 0xff,
    (trackLen >> 16) & 0xff,
    (trackLen >> 8) & 0xff,
    trackLen & 0xff,
  ]
  const bytes = new Uint8Array([...header, ...trackHeader, ...track])
  return Buffer.from(bytes).toString('base64')
}

export default function ReviewScreen() {
  const router = useRouter()
  const lesson = useLessonStore((s) => s.lesson)
  const sectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[sectionIndex]
  const latestTake = useSessionPlayStore((s) => s.latestTake)
  const clearLatestTake = useSessionPlayStore((s) => s.clearLatestTake)
  const [busy, setBusy] = useState(false)
  const [score, setScore] = useState<ScoreResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [exportState, setExportState] = useState<string>('Idle')
  const [sessionCount, setSessionCount] = useState<number | null>(null)

  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const sectionMidiBase64 =
    section && typeof section === 'object' && typeof (section as Record<string, unknown>).midi_base64 === 'string'
      ? ((section as Record<string, unknown>).midi_base64 as string)
      : null
  const midiBase64 = useMemo(
    () => sectionMidiBase64 ?? buildFallbackMidiBase64(lesson?.tempo, lesson?.key),
    [lesson?.key, lesson?.tempo, sectionMidiBase64],
  )

  const runScore = useCallback(async () => {
    if (!latestTake || latestTake.audioBytes.length === 0) {
      setError('No recording buffer found from Play step. Re-run Play and record a take.')
      setScore(null)
      return
    }
    if (!section) {
      setError('No section metadata found for scoring.')
      setScore(null)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await submitScore({
        recording_wav_base64: bytesToBase64(latestTake.audioBytes),
        recording_mime_type: latestTake.mimeType,
        section: {
          ...(section && typeof section === 'object' ? section : {}),
          tempo: lesson?.tempo,
          key: lesson?.key,
          beat_grid: lesson?.beat_grid ?? [],
          bar_timestamps: lesson?.bar_timestamps ?? [],
        },
        skill_nodes: ['pitch_accuracy', 'phrasing', 'timing'],
      })
      setScore(result)
      const targeted = ['pitch_accuracy', 'phrasing', 'timing']
      const targetedSet = new Set(targeted)
      await insertSessionRow({
        id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        song_title: typeof lesson?.song_title === 'string' ? lesson.song_title : null,
        artist: typeof lesson?.artist === 'string' ? lesson.artist : null,
        section_label:
          section && typeof section === 'object' && typeof (section as Record<string, unknown>).label === 'string'
            ? ((section as Record<string, unknown>).label as string)
            : null,
        date: new Date().toISOString(),
        coach_review: null,
        pitch_accuracy: result.pitch_accuracy,
        phrasing_score: result.phrasing_score,
        nodes_targeted: targeted,
      })
      await applyReviewSkillUpdates({
        node_scores: result.node_scores,
        targeted_node_ids: targeted,
      })
      await useSkillStore.getState().loadFromDb()
      const refreshed = useSkillStore.getState().nodes
      console.log(
        '[skill] SM-2 after review',
        refreshed
          .filter((n) => targetedSet.has(n.id))
          .map((n) => ({ id: n.id, score: n.score, next_review_date: n.next_review_date, interval_days: n.interval_days })),
      )
      setSessionCount(await getSessionCount())
    } catch (e) {
      setScore(null)
      setError(e instanceof Error ? e.message : 'Score request failed')
    } finally {
      setBusy(false)
    }
  }, [latestTake, lesson?.artist, lesson?.song_title, lesson?.bar_timestamps, lesson?.beat_grid, lesson?.key, lesson?.tempo, section])

  useEffect(() => {
    void getSessionCount().then(setSessionCount).catch(() => {})
  }, [])

  const exportMidi = useCallback(async () => {
    if (!midiBase64) {
      setExportState('No MIDI/GP5 payload found for this section.')
      return
    }
    try {
      if (Platform.OS === 'web') {
        const dataUrl = `data:audio/midi;base64,${midiBase64}`
        const opened = await WebBrowser.openBrowserAsync(dataUrl)
        setExportState(`Export opened (${opened.type}).`)
        return
      }
      const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
      if (!dir) throw new Error('No writable directory for export')
      const path = `${dir}harmoniq-section-${sectionIndex + 1}.mid`
      await FileSystem.writeAsStringAsync(path, midiBase64, { encoding: FileSystem.EncodingType.Base64 })
      const canShare = await Sharing.isAvailableAsync()
      if (!canShare) throw new Error('Share sheet unavailable on this device')
      await Sharing.shareAsync(path, { mimeType: 'audio/midi', dialogTitle: 'Export MIDI' })
      setExportState('MIDI exported via share sheet.')
    } catch (e) {
      setExportState(`Export failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }, [midiBase64, sectionIndex])

  const finish = () => {
    clearLatestTake()
    router.replace('/(tabs)')
  }

  return (
    <SessionStepScreen
      title="Review"
      subtitle="Score upload + phrasing visualizer shell + MIDI export."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Done"
      onNext={finish}
    >
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
        <Text className="mt-2 font-sans text-[11px] text-muted-brown">
          Terracotta = user take, amber = reference guide. Beat lines are static placeholders in this commit.
        </Text>
      </View>

      <View className="mt-3 flex-row flex-wrap items-center gap-2">
        <Pressable
          onPress={() => void runScore()}
          disabled={busy}
          className="rounded-lg bg-amber-accent/90 px-4 py-2 disabled:opacity-40"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">{busy ? 'Scoring…' : 'Run score'}</Text>
        </Pressable>
        <Pressable
          onPress={() => void exportMidi()}
          className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2"
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-wood-900">Export MIDI</Text>
        </Pressable>
      </View>

      <Text className="mt-2 font-mono text-[11px] text-muted-brown">{exportState}</Text>

      {error ? (
        <View className="mt-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2">
          <Text className="font-sans text-sm text-danger">{error}</Text>
          <Pressable
            onPress={() => void runScore()}
            className="mt-2 self-start rounded-md border border-danger/40 px-3 py-1.5"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-xs text-danger">Retry score</Text>
          </Pressable>
        </View>
      ) : null}

      {score ? (
        <View className="mt-3 rounded-lg border border-success/30 bg-success/10 px-3 py-2">
          <Text className="font-sans-medium text-sm text-wood-900">Score summary (numeric)</Text>
          <Text className="mt-1 font-mono text-xs text-wood-900">
            pitch_accuracy={score.pitch_accuracy.toFixed(3)} | phrasing_score={score.phrasing_score.toFixed(3)}
          </Text>
          <Text className="mt-1 font-mono text-xs text-wood-900">
            rushing_score={score.rushing_score.toFixed(3)} | bend_error_cents={score.bend_pitch_error_cents.toFixed(1)}
          </Text>
        </View>
      ) : null}

      {!sectionMidiBase64 && (tabs.full || tabs.skeleton || tabs.alt) ? (
        <Text className="mt-2 font-sans text-[11px] text-muted-brown">
          Using generated fallback MIDI for export (section has no `midi_base64` yet).
        </Text>
      ) : null}

      <Text className="mt-3 font-sans text-[11px] text-muted-brown">
        Recording buffer: {latestTake ? `${(latestTake.durationMs / 1000).toFixed(1)}s / ${latestTake.audioBytes.length} bytes` : 'none'}
      </Text>
      <Text className="mt-1 font-sans text-[11px] text-muted-brown">
        Persisted sessions (local DB): {sessionCount ?? '...'}
      </Text>
    </SessionStepScreen>
  )
}

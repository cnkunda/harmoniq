import { Audio } from 'expo-av'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Platform, Pressable, ScrollView, Switch, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Music } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { CoachNote } from '@/components/CoachNote'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LickCard } from '@/components/LickCard'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { PitchIndicator } from '@/components/PitchIndicator'
import { SessionStepper } from '@/components/SessionStepper'
import { SkillGraph } from '@/components/SkillGraph'
import { StemMixer } from '@/components/StemMixer'
import { TabView } from '@/components/TabView'
import { toast } from '@/components/ToastConfig'
import { WaveformVisualizer } from '@/components/WaveformVisualizer'
import { WoodGradient } from '@/components/WoodGradient'
import { createStemMixer } from '@/src/audio/Mixer'
import { BACKING_TRACKS } from '@/src/constants/backingTracks'
import { STEM_MIXER_DEV_STEMS } from '@/src/constants/stemMixerDev'
import { RUNTIME_DIAG_THRESHOLDS } from '@/src/constants/alphaTabRuntimeDiag'
import { API_BASE_URL } from '@/src/config'
import { useAlphaTabRuntimeDiagStore } from '@/src/stores/alphaTabRuntimeDiagStore'
import type { PitchReading } from '@/src/pitch/pitchTypes'
import { usePitchStream } from '@/src/pitch/usePitchStream'

const WOOD_SWATCHES = [
  { label: 'wood-900', className: 'bg-wood-900' },
  { label: 'wood-800', className: 'bg-wood-800' },
  { label: 'wood-700', className: 'bg-wood-700' },
  { label: 'wood-600', className: 'bg-wood-600' },
  { label: 'wood-500', className: 'bg-wood-500' },
] as const

function Swatch({ label, className }: { label: string; className: string }) {
  return (
    <View className="mb-3 w-[48%]">
      <View className={`h-14 rounded-lg border border-wood-600 ${className}`} />
      <Text className="mt-1 font-mono text-[10px] text-cream/80">{label}</Text>
    </View>
  )
}

/** Commit 61 — live AlphaTab runtime diagnostics (`__DEV__` Design tab only). */
function AlphaTabRuntimeDiagDevSection() {
  const latest = useAlphaTabRuntimeDiagStore((s) => s.latest)
  const clear = useAlphaTabRuntimeDiagStore((s) => s.clear)

  return (
    <View className="mb-6 rounded-xl border border-wood-600/60 bg-wood-900/40 p-4">
      <Text className="mb-1 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
        AlphaTab runtime diagnostics (Commit 61)
      </Text>
      <Text className="mb-3 font-sans text-xs text-muted-brown">
        Run Listen or Play with diagnostics enabled; values refresh every {5000 / 1000}s.         Thresholds in{' '}
        <Text className="font-mono text-[11px] text-cream/90">docs/MANUAL_QA.md</Text> (AlphaTab runtime telemetry).
      </Text>
      {!latest ? (
        <Text className="font-mono text-[11px] text-cream/70">No snapshot yet — open a session tab and play.</Text>
      ) : (
        <>
          <Text className="mb-2 font-mono text-[11px] leading-5 text-cream/90" selectable>
            driftMs: {latest.driftMs != null ? latest.driftMs.toFixed(1) : '—'} (fail &gt;{' '}
            {RUNTIME_DIAG_THRESHOLDS.driftMsFail})
            {'\n'}
            noteEventHz: {(latest.noteEventHz ?? 0).toFixed(1)} (fail &gt; {RUNTIME_DIAG_THRESHOLDS.noteEventHzFail})
            {'\n'}
            renderFps: {(latest.renderFps ?? 0).toFixed(1)} (fail &gt; {RUNTIME_DIAG_THRESHOLDS.renderFpsFail})
            {'\n'}
            bridgeLatencyMs: {latest.bridgeLatencyMs != null ? latest.bridgeLatencyMs.toFixed(0) : '—'} (native RTT;
            fail &gt; {RUNTIME_DIAG_THRESHOLDS.bridgeLatencyMsFail}){'\n'}
            source: {latest.source} · window {latest.windowMs}ms{'\n'}
            breachFlags: {latest.breachFlags.length ? latest.breachFlags.join(', ') : '(none)'}
          </Text>
          {latest.breachFlags.length ? (
            <Text className="mb-2 font-sans-medium text-xs text-danger">
              FAIL breach — see docs/MANUAL_QA.md (AlphaTab runtime telemetry → Thresholds).
            </Text>
          ) : null}
        </>
      )}
      <Pressable
        onPress={() => clear()}
        className="mt-2 self-start rounded-lg border border-wood-600/60 bg-wood-800/80 px-3 py-2"
        accessibilityRole="button"
      >
        <Text className="font-sans-medium text-xs text-cream">Clear snapshot</Text>
      </Pressable>
    </View>
  )
}

/** Phase 0 — sequential `expo-av` load/play for every bundled backing track */
function BackingTrackDevSection() {
  const [status, setStatus] = useState<string>('Idle')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    console.log('[Harmoniq] API_BASE_URL =', API_BASE_URL)
  }, [])

  const runSmokeTest = useCallback(async () => {
    setBusy(true)
    setStatus('Running…')
    try {
      await Audio.setAudioModeAsync({
        playsInSilentModeIOS: true,
        allowsRecordingIOS: false,
      })
      for (const t of BACKING_TRACKS) {
        const { sound } = await Audio.Sound.createAsync(t.source, { shouldPlay: false })
        await sound.playAsync()
        await new Promise((r) => setTimeout(r, 450))
        await sound.stopAsync()
        await sound.unloadAsync()
      }
      setStatus(`OK — played ${BACKING_TRACKS.length} tracks`)
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }, [])

  return (
    <View className="mb-6 rounded-xl border border-wood-600/60 bg-wood-900/40 p-4">
      <Text className="mb-1 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
        Commit 0.5 — API + backing tracks
      </Text>
      <Text className="mb-2 font-mono text-[11px] leading-snug text-cream/90" selectable>
        API_BASE_URL: {API_BASE_URL}
      </Text>
      <Text className="mb-3 font-sans text-xs text-muted-brown">
        Set EXPO_PUBLIC_API_URL in a root `.env` (see `.env.example`) for a LAN backend; restart Metro after
        changes.
      </Text>
      <Pressable
        onPress={runSmokeTest}
        disabled={busy}
        className={`items-center rounded-lg py-3 ${busy ? 'bg-wood-700' : 'bg-amber-accent/90'}`}
      >
        <Text className={`font-sans-medium text-sm ${busy ? 'text-muted-brown' : 'text-wood-900'}`}>
          {busy ? 'Playing test sequence…' : 'Smoke-test all 5 backing tracks (expo-av)'}
        </Text>
      </Pressable>
      <Text className="mt-2 font-mono text-[11px] text-cream/80">{status}</Text>
    </View>
  )
}

/** Commit 14 — parallel stems (native) / Web Audio gains (web); bundled dev WAVs */
function StemMixerDevSection() {
  const mixerRef = useRef<ReturnType<typeof createStemMixer> | null>(null)
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [guitarOn, setGuitarOn] = useState(true)
  const [drumsOn, setDrumsOn] = useState(true)
  const [status, setStatus] = useState<string>('Idle')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const mixer = createStemMixer()
    mixerRef.current = mixer
    let cancelled = false

    const boot = async () => {
      setBusy(true)
      setStatus('Loading stems…')
      try {
        await mixer.load(STEM_MIXER_DEV_STEMS)
        if (cancelled) {
          await mixer.unload().catch((err: unknown) => console.error('[StemMixerDev] unload after cancel', err))
          return
        }
        setReady(true)
        setStatus('Loaded — press Play')
        console.log('[StemMixerDev] load OK')
      } catch (e) {
        console.error('[StemMixerDev] load failed', e)
        if (!cancelled) {
          setStatus(`Load error: ${e instanceof Error ? e.message : String(e)}`)
        }
      } finally {
        if (!cancelled) {
          setBusy(false)
        }
      }
    }

    void boot()

    return () => {
      cancelled = true
      mixer.unload().catch((err: unknown) => console.error('[StemMixerDev] unload', err))
      mixerRef.current = null
    }
  }, [])

  useEffect(() => {
    const m = mixerRef.current
    if (!m || !ready) return
    void m.setStemGain('guitar', guitarOn ? 1 : 0).catch((err: unknown) => console.error('[StemMixerDev] guitar gain', err))
  }, [guitarOn, ready])

  useEffect(() => {
    const m = mixerRef.current
    if (!m || !ready) return
    void m.setStemGain('drums', drumsOn ? 1 : 0).catch((err: unknown) => console.error('[StemMixerDev] drums gain', err))
  }, [drumsOn, ready])

  const togglePlay = async () => {
    const m = mixerRef.current
    if (!m || !ready) return
    setBusy(true)
    try {
      if (playing) {
        await m.pause()
        setPlaying(false)
        setStatus('Paused')
      } else {
        await m.play()
        setPlaying(true)
        setStatus('Playing (loop)')
      }
    } catch (e) {
      console.error('[StemMixerDev] play/pause', e)
      setStatus(`Error: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className="mb-6 rounded-xl border border-wood-600/60 bg-wood-900/40 p-4">
      <Text className="mb-1 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
        Commit 14 — multi-stem mixer (native + web)
      </Text>
      <Text className="mb-3 font-sans text-xs text-muted-brown">
        Two bundled WAVs (44.1 kHz). Toggle Guitar / Drums while playing; should not crash. Logs: StemMixer.*
      </Text>

      <View className="mb-3 flex-row items-center justify-between">
        <Text className="font-sans text-sm text-cream">Guitar</Text>
        <Switch
          value={guitarOn}
          onValueChange={setGuitarOn}
          disabled={!ready || busy}
          trackColor={{ false: '#5c4a38', true: '#D4860A80' }}
          thumbColor={guitarOn ? '#F0DEB4' : '#7A5A3B'}
        />
      </View>
      <View className="mb-4 flex-row items-center justify-between">
        <Text className="font-sans text-sm text-cream">Drums</Text>
        <Switch
          value={drumsOn}
          onValueChange={setDrumsOn}
          disabled={!ready || busy}
          trackColor={{ false: '#5c4a38', true: '#D4860A80' }}
          thumbColor={drumsOn ? '#F0DEB4' : '#7A5A3B'}
        />
      </View>

      <Pressable
        onPress={togglePlay}
        disabled={!ready || busy}
        className={`items-center rounded-lg py-3 ${!ready || busy ? 'bg-wood-700' : 'bg-amber-accent/90'}`}
      >
        <Text className={`font-sans-medium text-sm ${!ready || busy ? 'text-muted-brown' : 'text-wood-900'}`}>
          {!ready ? 'Loading…' : playing ? 'Pause' : 'Play'}
        </Text>
      </Pressable>
      <Text className="mt-2 font-mono text-[11px] text-cream/80">{status}</Text>
    </View>
  )
}

/** Commits 15–16 — mic capture + pitch estimate (web AudioWorklet · native JSI buffers) */
function PitchWorkletDevSection() {
  const { start, stop } = usePitchStream()
  const [active, setActive] = useState(false)
  const [status, setStatus] = useState('Idle')
  const [note, setNote] = useState('--')
  const [hz, setHz] = useState<number | null>(null)
  const [cents, setCents] = useState<number | null>(null)
  const [permissionBlocked, setPermissionBlocked] = useState(false)
  const [busy, setBusy] = useState(false)

  const stopStream = useCallback(async () => {
    try {
      await stop()
      setStatus('Mic stopped')
    } catch (error) {
      console.error('[PitchDev] stop failed', error)
      setStatus(`Stop error: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setActive(false)
    }
  }, [stop])

  const startStream = useCallback(async () => {
    setBusy(true)
    setPermissionBlocked(false)
    setStatus('Starting mic…')
    try {
      await start((reading: PitchReading) => {
        setNote(reading.noteName)
        setHz(reading.hz ?? null)
        setCents(reading.cents)
      })
      setActive(true)
      setStatus('Listening')
      console.log('[PitchDev] stream started')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      console.error('[PitchDev] start failed', error)
      if (message === 'MIC_PERMISSION_DENIED') {
        setPermissionBlocked(true)
        setStatus('Permission denied')
      } else {
        setStatus(`Start error: ${message}`)
      }
      setActive(false)
    } finally {
      setBusy(false)
    }
  }, [start])

  useEffect(() => {
    return () => {
      void stopStream()
    }
  }, [stopStream])

  const toggle = async () => {
    setBusy(true)
    try {
      if (active) {
        await stopStream()
      } else {
        await startStream()
      }
    } finally {
      setBusy(false)
    }
  }

  const permissionHint =
    Platform.OS === 'web'
      ? 'Your browser is blocking mic access — click the lock icon to enable it.'
      : 'Microphone access is off — enable it in system settings for Harmoniq, then retry.'

  if (permissionBlocked) {
    return (
      <View className="mb-6 rounded-xl border border-danger/80 bg-wood-900/40 p-4">
        <Text className="mb-1 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
          Mic + pitch (dev)
        </Text>
        <Text className="mb-3 font-sans text-sm text-cream">{permissionHint}</Text>
        <Pressable onPress={startStream} disabled={busy} className="items-center rounded-lg bg-amber-accent/90 py-3">
          <Text className="font-sans-medium text-sm text-wood-900">{busy ? 'Retrying…' : 'Retry mic access'}</Text>
        </Pressable>
      </View>
    )
  }

  const platformHint =
    Platform.OS === 'web'
      ? 'Web: requires HTTPS (or localhost). Stop releases mic and AudioContext.'
      : 'iOS/Android: use an Expo dev build (react-native-audio-api is not in Expo Go). Rough latency ~50–100ms buffer + UI.'

  return (
    <View className="mb-6 rounded-xl border border-wood-600/60 bg-wood-900/40 p-4">
      <Text className="mb-1 font-sans-medium text-xs uppercase tracking-wider text-amber-light">Mic + pitch (dev)</Text>
      <Text className="mb-3 font-sans text-xs text-muted-brown">
        Start mic and hum or play a steady pitch. Live note readout uses the same estimator on web (worklet) and native
        (PCM callbacks). {platformHint}
      </Text>
      <View className="mb-4 rounded-lg border border-wood-600 px-3 py-2">
        <Text className="font-mono text-xl text-cream">Note: {note}</Text>
        <Text className="font-mono text-xs text-cream/80">
          {hz ? `${hz.toFixed(1)} Hz` : '--'} {cents !== null ? `· ${cents > 0 ? '+' : ''}${cents} cents` : ''}
        </Text>
      </View>
      <Pressable
        onPress={toggle}
        disabled={busy}
        className={`items-center rounded-lg py-3 ${busy ? 'bg-wood-700' : 'bg-amber-accent/90'}`}
      >
        <Text className={`font-sans-medium text-sm ${busy ? 'text-muted-brown' : 'text-wood-900'}`}>
          {busy ? 'Working…' : active ? 'Stop mic' : 'Start mic'}
        </Text>
      </Pressable>
      <Text className="mt-2 font-mono text-[11px] text-cream/80">{status}</Text>
    </View>
  )
}

/** Phase 0 — AnimatedPressable, skeletons, empty/error feedback, toast */
function FeedbackLayerDevSection() {
  return (
    <View className="mb-6 rounded-xl border border-wood-600/60 bg-wood-900/40 p-4">
      <Text className="mb-3 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
        Phase 0 — Feedback layer
      </Text>

      <Text className="mb-2 font-sans text-xs text-muted-brown">AnimatedPressable (spring + haptics)</Text>
      <View className="mb-4 gap-2">
        <AnimatedPressable haptic="light" className="rounded-lg bg-amber-accent/90 px-4 py-2.5">
          <Text className="text-center font-sans-medium text-sm text-wood-900">1 · Light impact</Text>
        </AnimatedPressable>
        <AnimatedPressable haptic="medium" className="rounded-lg bg-amber-accent/90 px-4 py-2.5">
          <Text className="text-center font-sans-medium text-sm text-wood-900">2 · Medium impact</Text>
        </AnimatedPressable>
        <AnimatedPressable haptic="heavy" className="rounded-lg bg-amber-accent/90 px-4 py-2.5">
          <Text className="text-center font-sans-medium text-sm text-wood-900">3 · Heavy impact</Text>
        </AnimatedPressable>
        <AnimatedPressable haptic="none" className="rounded-lg bg-wood-700 px-4 py-2.5">
          <Text className="text-center font-sans-medium text-sm text-cream">4 · No haptic (scale only)</Text>
        </AnimatedPressable>
        <AnimatedPressable
          haptic="light"
          className="rounded-lg border-2 border-amber-accent/50 bg-wood-800 px-4 py-2.5"
        >
          <Text className="text-center font-sans-medium text-sm text-amber-light">5 · Light + outline style</Text>
        </AnimatedPressable>
      </View>

      <Text className="mb-2 font-sans text-xs text-muted-brown">LoadingSkeleton</Text>
      <View className="mb-4 gap-3">
        <LoadingSkeleton width="100%" height={14} borderRadius={6} />
        <LoadingSkeleton width={120} height={40} borderRadius={12} />
      </View>

      <Text className="mb-2 font-sans text-xs text-muted-brown">EmptyState</Text>
      <View className="mb-4 overflow-hidden rounded-xl border border-wood-600/40 bg-wood-900/30 py-2">
        <EmptyState
          Icon={Music}
          heading="No licks yet"
          subtext="Save a phrase from analysis or practice to see it here."
          ctaLabel="Browse lessons"
          onCta={() => toast.success('EmptyState CTA pressed')}
        />
      </View>

      <Text className="mb-2 font-sans text-xs text-muted-brown">ErrorBanner (warning · error · info)</Text>
      <View className="mb-4 gap-3">
        <ErrorBanner message="Transcription confidence is low — tab may be approximate." variant="warning" />
        <ErrorBanner message="Could not reach the practice backend." variant="error" dismissible={false} />
        <ErrorBanner
          message="Tip: plug in headphones for lowest latency."
          variant="info"
          action={{ label: 'OK', onPress: () => toast.success('Banner action') }}
        />
      </View>

      <Text className="mb-2 font-sans text-xs text-muted-brown">Toast helpers</Text>
      <View className="flex-row flex-wrap gap-2">
        <AnimatedPressable
          haptic="light"
          className="rounded-lg bg-success/90 px-4 py-2.5"
          onPress={() => toast.success('Saved — wood toast')}
        >
          <Text className="font-sans-medium text-sm text-wood-900">toast.success</Text>
        </AnimatedPressable>
        <AnimatedPressable
          haptic="medium"
          className="rounded-lg bg-danger/80 px-4 py-2.5"
          onPress={() => toast.error('Something went wrong (demo)')}
        >
          <Text className="font-sans-medium text-sm text-cream">toast.error</Text>
        </AnimatedPressable>
      </View>
    </View>
  )
}

export default function DesignPreviewScreen() {
  if (!__DEV__) {
    return null
  }

  return (
    <WoodGradient variant="background" className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
          <View className="px-4 pb-10 pt-2">
            <Text className="mb-1 font-serif text-2xl text-cream">Design preview</Text>
            <Text className="mb-6 font-sans text-sm text-muted-brown">
              Design tokens, env and backing tracks, shared feedback layer, and component stubs (Phase 0).
            </Text>

            <AlphaTabRuntimeDiagDevSection />
            <FeedbackLayerDevSection />
            <PitchWorkletDevSection />
            <StemMixerDevSection />
            <BackingTrackDevSection />

            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
              Wood scale
            </Text>
            <View className="mb-6 flex-row flex-wrap justify-between">
              {WOOD_SWATCHES.map((s) => (
                <Swatch key={s.label} label={s.label} className={s.className} />
              ))}
            </View>

            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
              Amber, cream, ivory
            </Text>
            <View className="mb-6 flex-row flex-wrap justify-between">
              <Swatch label="amber-accent" className="bg-amber-accent" />
              <Swatch label="amber-light" className="bg-amber-light" />
              <Swatch label="cream" className="bg-cream" />
              <Swatch label="cream-dark" className="bg-cream-dark" />
              <Swatch label="ivory" className="bg-ivory" />
              <Swatch label="muted-brown (text token)" className="bg-muted-brown" />
            </View>

            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
              Semantic
            </Text>
            <View className="mb-6 flex-row flex-wrap justify-between">
              <Swatch label="danger" className="bg-danger" />
              <Swatch label="success" className="bg-success" />
            </View>

            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
              WoodGradient (card variant)
            </Text>
            <WoodGradient variant="card" className="mb-6 min-h-[88px] rounded-xl border border-wood-600/50 p-4">
              <Text className="font-sans text-sm text-cream/90">
                Card gradient — same component as screen backgrounds, variant "card".
              </Text>
            </WoodGradient>

            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wider text-amber-light">
              Component stubs
            </Text>
            <View className="gap-3">
              <CoachNote text="Preview: coach copy uses the warm wood panel and amber accent rail." />
              <SessionStepper />
              <WaveformVisualizer />
              <StemMixer />
              <PitchIndicator />
              <LickCard />
              <SkillGraph />
              <TabView />
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}

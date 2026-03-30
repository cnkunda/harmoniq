import { Audio } from 'expo-av'
import { useCallback, useEffect, useState } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'
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
import { BACKING_TRACKS } from '@/src/constants/backingTracks'
import { API_BASE_URL } from '@/src/config'

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

            <FeedbackLayerDevSection />
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
              <CoachNote />
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

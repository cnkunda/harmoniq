import { useRouter } from 'expo-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Platform, Pressable, Switch, Text, View } from 'react-native'

import { DemoTourCallout } from '@/components/DemoTourCallout'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { noiseGateThresholdFromAmbientSamples } from '@/src/audio/noiseGate'
import { sessionHref } from '@/src/constants/sessionFlow'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import {
  MIC_CALIBRATION_PROFILES,
  type MicCalibrationProfileId,
  useSessionPrefsStore,
} from '@/src/stores/sessionPrefsStore'

const E2_TARGET_MIDI = 40
const IN_TUNE_CENTS = 15
const CALIBRATION_MS = 3000

function centsFromHzToTargetMidi(hz: number, targetMidi: number): number {
  const midiFloat = 69 + 12 * Math.log2(hz / 440)
  return (midiFloat - targetMidi) * 100
}

export default function TuneScreen() {
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const { start, stop } = usePitchStream()

  const hydrated = useSessionPrefsStore((s) => s.hydrated)
  const activeMicProfile = useSessionPrefsStore((s) => s.activeMicProfile)
  const gateForProfile = useSessionPrefsStore((s) => s.calibrationGateRmsByProfile[s.activeMicProfile])
  const setCalibrationGateForProfile = useSessionPrefsStore((s) => s.setCalibrationGateForProfile)
  const setActiveMicProfile = useSessionPrefsStore((s) => s.setActiveMicProfile)
  const setSkipTuneStep = useSessionPrefsStore((s) => s.setSkipTuneStep)

  const [rms, setRms] = useState(0)
  const [hz, setHz] = useState<number | null>(null)
  const [cents, setCents] = useState<number | null>(null)
  const [noteName, setNoteName] = useState('')
  const [calibrating, setCalibrating] = useState(false)
  const [skipTuneNextLaunch, setSkipTuneNextLaunch] = useState(false)

  const calEndAtRef = useRef(0)
  const calSamplesRef = useRef<number[]>([])

  const forwardToListen = async () => {
    if (skipTuneNextLaunch) await setSkipTuneStep(true)
    router.push(sessionHref('listen'))
  }

  useEffect(() => {
    let alive = true
    void (async () => {
      await start((reading) => {
        if (!alive) return
        const r = typeof reading.rms === 'number' && Number.isFinite(reading.rms) ? reading.rms : 0
        setRms(r)
        setNoteName(reading.noteName ?? '')
        const h = typeof reading.hz === 'number' && Number.isFinite(reading.hz) && reading.hz > 0 ? reading.hz : null
        setHz(h)
        if (h != null) setCents(centsFromHzToTargetMidi(h, E2_TARGET_MIDI))
        else setCents(null)

        const endAt = calEndAtRef.current
        if (endAt > 0 && Date.now() >= endAt) {
          const thresh = noiseGateThresholdFromAmbientSamples(calSamplesRef.current)
          const pid = useSessionPrefsStore.getState().activeMicProfile
          void useSessionPrefsStore.getState().setCalibrationGateForProfile(pid, thresh)
          calEndAtRef.current = 0
          calSamplesRef.current = []
          setCalibrating(false)
        } else if (endAt > 0 && Date.now() < endAt) {
          calSamplesRef.current.push(r)
        }
      })
    })()
    return () => {
      alive = false
      calEndAtRef.current = 0
      calSamplesRef.current = []
      void stop()
    }
  }, [start, stop])

  const beginCalibration = useCallback(() => {
    calSamplesRef.current = []
    calEndAtRef.current = Date.now() + CALIBRATION_MS
    setCalibrating(true)
  }, [])

  const gateDisplay =
    typeof gateForProfile === 'number' && Number.isFinite(gateForProfile) ? gateForProfile.toFixed(4) : '—'

  const tunerOk =
    hz != null && cents != null && Math.abs(cents) <= IN_TUNE_CENTS && rms > 0.008

  return (
    <SessionStepScreen
      title="Tune & room noise"
      subtitle={
        isDemo
          ? DEMO_TOUR_SUBTITLE.tune
          : 'Calibrate ambient noise for Play scoring, then tune your low E string before practice.'
      }
      showBack
      backLabel="Close"
      onBack={() => {
        if (router.canGoBack()) router.back()
        else router.replace('/(tabs)')
      }}
      showNext={false}
      nextLabel="Continue"
      onNext={() => {}}
    >
      {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.tune}</DemoTourCallout> : null}
      <View className="gap-6 pb-6">
        <Text className="font-sans text-sm text-muted-brown">
          Mic profile (saved per environment). Calibration stores an RMS gate in SQLite with +6 dB headroom.
        </Text>

        <View className="flex-row flex-wrap gap-2">
          {MIC_CALIBRATION_PROFILES.map((id) => (
            <Pressable
              key={id}
              onPress={() => void setActiveMicProfile(id)}
              className={`rounded-full border px-4 py-2 ${
                activeMicProfile === id ? 'border-amber-accent bg-amber-accent/15' : 'border-wood-600/40 bg-cream-dark/40'
              }`}
              accessibilityRole="button"
            >
              <Text className="font-sans text-xs text-wood-900">{id.replace('-', ' ')}</Text>
            </Pressable>
          ))}
        </View>

        <Pressable
          onPress={beginCalibration}
          disabled={calibrating || !hydrated}
          className={`rounded-xl border border-wood-600/35 bg-cream-dark/50 px-4 py-3 ${calibrating ? 'opacity-60' : ''}`}
          accessibilityRole="button"
        >
          <Text className="font-sans-medium text-center text-wood-900">
            {calibrating ? 'Measuring ambient noise…' : 'Measure ambient noise (3 sec)'}
          </Text>
        </Pressable>

        <Text className="font-sans text-xs text-muted-brown">
          Gate for <Text className="font-sans-medium text-wood-800">{activeMicProfile}</Text>:{' '}
          <Text className="font-mono text-wood-900">{gateDisplay}</Text> RMS
        </Text>

        <View className="rounded-2xl border border-wood-600/35 bg-cream-dark/35 p-4">
          <Text className="font-serif text-xl text-wood-900">Low E (E2)</Text>
          <Text className="mt-1 font-sans text-sm text-muted-brown">
            Bring the open low E within ±{IN_TUNE_CENTS} cents. Acceptance check for Play entry.
          </Text>
          <Text className="mt-4 font-mono text-4xl text-amber-accent">{hz != null ? hz.toFixed(1) : '—'} Hz</Text>
          <Text className="mt-2 font-mono text-lg text-wood-800">{cents != null ? `${cents > 0 ? '+' : ''}${cents.toFixed(0)}¢` : '—'}</Text>
          <Text className="mt-2 font-sans text-sm text-muted-brown">{noteName || 'Play the open low E string…'}</Text>
          {tunerOk ? (
            <Text className="mt-3 font-sans text-sm text-success">In range — ready for Play scoring.</Text>
          ) : null}
        </View>

        <View className="flex-row items-center justify-between gap-3 rounded-xl border border-wood-600/25 bg-cream-dark/40 px-3 py-3">
          <Text className="flex-1 font-sans text-sm text-wood-900">Skip tuner on future sessions</Text>
          <Switch value={skipTuneNextLaunch} onValueChange={setSkipTuneNextLaunch} />
        </View>

        {typeof __DEV__ !== 'undefined' && __DEV__ ? (
          <View className="rounded-lg border border-dashed border-wood-600/40 px-3 py-2">
            <Text className="font-mono text-xs text-wood-700">
              noiseGateThresholdRms (active profile): {gateDisplay} · live RMS: {rms.toFixed(4)}{' '}
              {Platform.OS === 'web' ? '(web)' : '(native)'}
            </Text>
          </View>
        ) : null}

        <View className="gap-3">
          <Pressable
            onPress={() => void forwardToListen()}
            disabled={!tunerOk && !skipTuneNextLaunch}
            className={`rounded-xl py-3 ${tunerOk || skipTuneNextLaunch ? 'bg-success/90' : 'bg-wood-600/30'}`}
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-wood-900">
              Looks good — continue to Listen
            </Text>
          </Pressable>
          <Pressable onPress={() => void forwardToListen()} className="rounded-xl py-3" accessibilityRole="button">
            <Text className="text-center font-sans text-sm text-muted-brown underline">Skip for now</Text>
          </Pressable>
        </View>
      </View>
    </SessionStepScreen>
  )
}

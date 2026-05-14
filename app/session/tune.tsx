import { useRouter } from 'expo-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import Svg, { Circle, G } from 'react-native-svg'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { FormCheckbox } from '@/components/FormCheckbox'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { noiseGateThresholdFromAmbientSamples } from '@/src/audio/noiseGate'
import colors from '@/src/constants/colors'
import { SESSION_PLAYBACK_CARD_CLASS } from '@/src/constants/sessionPlaybackCard'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { usePitchStream } from '@/src/pitch/usePitchStream'
import {
    MIC_CALIBRATION_PROFILES,
    type MicCalibrationProfileId,
    useSessionPrefsStore,
} from '@/src/stores/sessionPrefsStore'

const E2_TARGET_MIDI = 40
const IN_TUNE_CENTS = 15
const CALIBRATION_MS = 3000
const TUNER_RING_R = 82
const TUNER_RING_STROKE = 7
const TUNER_RING_C = 2 * Math.PI * TUNER_RING_R
const CENTS_UI_CLAMP = 50

const SECTION_EYEBROW_CLASS = 'font-sans-medium text-xs uppercase tracking-wide text-amber-accent'

function centsFromHzToTargetMidi(hz: number, targetMidi: number): number {
  const midiFloat = 69 + 12 * Math.log2(hz / 440)
  return (midiFloat - targetMidi) * 100
}

function micProfileLabel(id: MicCalibrationProfileId): string {
  return id === 'quiet-acoustic' ? 'Quiet acoustic' : 'Electric unplugged'
}

export default function TuneScreen() {
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const { start, stop } = usePitchStream()

  const hydrated = useSessionPrefsStore((s) => s.hydrated)
  const activeMicProfile = useSessionPrefsStore((s) => s.activeMicProfile)
  const gateForProfile = useSessionPrefsStore((s) => s.calibrationGateRmsByProfile[s.activeMicProfile])
  const setActiveMicProfile = useSessionPrefsStore((s) => s.setActiveMicProfile)
  const setSkipTuneStep = useSessionPrefsStore((s) => s.setSkipTuneStep)

  const [rms, setRms] = useState(0)
  const [hz, setHz] = useState<number | null>(null)
  const [cents, setCents] = useState<number | null>(null)
  const [noteName, setNoteName] = useState('')
  const [calibrating, setCalibrating] = useState(false)
  const [dontShowAgain, setDontShowAgain] = useState(false)

  const calEndAtRef = useRef(0)
  const calSamplesRef = useRef<number[]>([])

  const exitSession = () => {
    if (router.canGoBack()) router.back()
    else router.replace('/(tabs)')
  }

  const forwardToListen = async () => {
    if (dontShowAgain) await setSkipTuneStep(true)
    router.push('/session/orient')
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

  const gateCalibrated = typeof gateForProfile === 'number' && Number.isFinite(gateForProfile) && gateForProfile > 0

  const tunerOk =
    hz != null && cents != null && Math.abs(cents) <= IN_TUNE_CENTS && rms > 0.008

  const ringProgress =
    cents != null ? Math.max(0, 1 - Math.min(1, Math.abs(cents) / CENTS_UI_CLAMP)) : 0
  const ringDash = TUNER_RING_C * ringProgress

  const centsForMeter =
    cents != null ? Math.max(-CENTS_UI_CLAMP, Math.min(CENTS_UI_CLAMP, cents)) : 0
  const centsMeterPct = (centsForMeter + CENTS_UI_CLAMP) / (2 * CENTS_UI_CLAMP)

  const canContinue = tunerOk || dontShowAgain

  const subtitle =
    isDemo
      ? DEMO_TOUR_SUBTITLE.tune
      : 'Calibrate ambient noise for accurate Play scoring, then verify your low E string is in tune.'

  const leftColumn = (
    <View className="min-w-0 flex-1 lg:max-w-[400px]">
      <Text className={SECTION_EYEBROW_CLASS}>Tuner</Text>

      <View className="mt-4 items-center">
        <View className="relative h-[220] w-[220] items-center justify-center">
          <Svg width={220} height={220} viewBox="0 0 220 220" style={{ position: 'absolute' }}>
            <Circle cx={110} cy={110} r={74} fill={colors.wood[900]} />
            <Circle
              cx={110}
              cy={110}
              r={TUNER_RING_R}
              stroke={colors.wood[600]}
              strokeWidth={TUNER_RING_STROKE}
              fill="none"
              opacity={0.45}
            />
            <G transform="rotate(-90 110 110)">
              <Circle
                cx={110}
                cy={110}
                r={TUNER_RING_R}
                stroke={colors.amber.accent}
                strokeWidth={TUNER_RING_STROKE}
                fill="none"
                strokeDasharray={`${ringDash} ${TUNER_RING_C}`}
                strokeLinecap="round"
              />
            </G>
          </Svg>
          <View className="items-center px-6">
            <Text className="font-serif text-4xl text-cream">E2</Text>
            <Text className="mt-1 font-serif text-lg text-cream/90">Low E</Text>
          </View>
        </View>

        <Text className="mt-5 font-mono text-base text-wood-900">{hz != null ? `${hz.toFixed(1)} Hz` : '—'}</Text>

        <View className="mt-5 w-full max-w-sm">
          <View className="relative h-9 justify-center">
            <View className="h-1 rounded-full bg-wood-600/35" />
            <View
              className="absolute h-3 w-0.5 rounded-full bg-wood-600/50"
              style={{ left: '50%', marginLeft: -1 }}
            />
            <View
              className="absolute -top-1 h-5 w-1 rounded-full bg-amber-accent"
              style={{ left: `${centsMeterPct * 100}%`, marginLeft: -2 }}
            />
          </View>
          <View className="mt-1.5 flex-row justify-between px-0.5">
            <Text className="font-mono text-[10px] text-muted-brown">−50</Text>
            <Text className="font-mono text-[10px] text-muted-brown">0</Text>
            <Text className="font-mono text-[10px] text-muted-brown">+50</Text>
          </View>
          <Text className="mt-2 text-center font-mono text-sm text-wood-800">
            {cents != null ? `${cents > 0 ? '+' : ''}${cents.toFixed(0)} cents` : '—'}
          </Text>
        </View>
      </View>

      <Text className="mt-6 text-center font-sans text-sm leading-relaxed text-muted-brown">
        {noteName ? `Heard: ${noteName}. ` : ''}Play the open low E string.
      </Text>
      {tunerOk ? (
        <Text className="mt-2 text-center font-sans text-sm text-success">In range — ready to continue.</Text>
      ) : null}
    </View>
  )

  const rightColumn = (
    <View className="min-w-0 flex-1 gap-6">
      <View>
        <Text className={SECTION_EYEBROW_CLASS}>Mic profile</Text>
        <View className="mt-2 flex-row flex-wrap gap-2">
          {MIC_CALIBRATION_PROFILES.map((id) => {
            const selected = activeMicProfile === id
            return (
              <AnimatedPressable
                key={id}
                haptic="light"
                onPress={() => void setActiveMicProfile(id)}
                className={`rounded-full border px-3 py-2 ${
                  selected ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/35 bg-cream-dark/35'
                }`}
                accessibilityRole="button"
                accessibilityState={{ selected }}
              >
                <Text className={`text-sm ${selected ? 'font-sans-medium text-wood-900' : 'font-sans text-muted-brown'}`}>
                  {micProfileLabel(id)}
                </Text>
              </AnimatedPressable>
            )
          })}
        </View>
      </View>

      <View className={SESSION_PLAYBACK_CARD_CLASS}>
        <View className="flex-row items-center justify-between gap-2">
          <Text className="font-sans-medium text-sm text-wood-900">Room noise gate</Text>
          <View
            className={`rounded-full px-2.5 py-1 ${gateCalibrated ? 'bg-success/20' : 'bg-wood-600/15'}`}
          >
            <Text
              className={`font-sans-medium text-[11px] uppercase tracking-wide ${gateCalibrated ? 'text-success' : 'text-muted-brown'}`}
            >
              {gateCalibrated ? 'Calibrated' : 'Not calibrated'}
            </Text>
          </View>
        </View>
        <Text className="mt-4 font-sans-medium text-[10px] uppercase tracking-wider text-muted-brown">
          RMS gate threshold
        </Text>
        <Text className="mt-1 font-mono text-base text-wood-900">{gateDisplay}</Text>
        <AnimatedPressable
          haptic="light"
          onPress={beginCalibration}
          disabled={calibrating || !hydrated}
          className={`mt-4 rounded-lg border border-wood-600/55 bg-cream-dark/60 py-3 ${calibrating ? 'opacity-60' : ''}`}
          accessibilityRole="button"
        >
          <Text className="text-center font-sans-medium text-sm text-wood-900">
            {calibrating ? 'Measuring…' : 'Measure (3 sec)'}
          </Text>
        </AnimatedPressable>
      </View>

      <View className={SESSION_PLAYBACK_CARD_CLASS}>
        <FormCheckbox
          checked={dontShowAgain}
          onCheckedChange={setDontShowAgain}
          label="Don't show this again — skip this step when I start future lessons."
        />
      </View>

      <View className="gap-3 pt-1">
        <AnimatedPressable
          haptic="medium"
          onPress={() => void forwardToListen()}
          disabled={!canContinue}
          className={`rounded-lg py-3 ${canContinue ? 'bg-amber-accent/90' : 'bg-wood-600/30'}`}
          accessibilityRole="button"
        >
          <Text
            className={`text-center font-sans-medium text-sm ${canContinue ? 'text-wood-900' : 'text-wood-700'}`}
          >
            Tune first, then continue
          </Text>
        </AnimatedPressable>
        <AnimatedPressable haptic="light" onPress={() => void forwardToListen()} accessibilityRole="button">
          <Text className="text-center font-sans text-sm text-muted-brown underline">Skip for now</Text>
        </AnimatedPressable>
      </View>
    </View>
  )

  return (
    <SessionStepScreen
      title="Tune & room noise"
      subtitle={subtitle}
      hideFooter
      showBack={false}
      backLabel="Close"
      onBack={exitSession}
      showNext={false}
      nextLabel="Continue"
      onNext={() => {}}
    >
      {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.tune}</DemoTourCallout> : null}

      <View className="mt-1 w-full max-w-5xl flex-col gap-8 self-center lg:max-w-6xl lg:flex-row lg:items-start lg:gap-10">
        {leftColumn}
        {rightColumn}
      </View>

      {typeof __DEV__ !== 'undefined' && __DEV__ ? (
        <View className="mt-6 rounded-lg border border-dashed border-wood-600/35 bg-cream-dark/40 px-3 py-2">
          <Text className="font-mono text-xs text-muted-brown">
            noiseGateThresholdRms ({activeMicProfile}): {gateDisplay} · live RMS: {rms.toFixed(4)}{' '}
            {Platform.OS === 'web' ? '(web)' : '(native)'}
          </Text>
        </View>
      ) : null}
    </SessionStepScreen>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { usePitchStream } from '@/src/pitch/usePitchStream'

const DEFAULT_NOISE_FLOOR = 0.012
const IN_TUNE_CENTS = 12

export type FretboardTunerState = {
  active: boolean
  calibrating: boolean
  inTune: boolean
  noteName: string
  cents: number | null
  hz: number | null
  rms: number
  noiseFloor: number
  statusText: string
}

export function useFretboardTuner(opts?: { disableWhen?: boolean }) {
  const { start, stop } = usePitchStream()
  const [active, setActive] = useState(false)
  const [calibrating, setCalibrating] = useState(false)
  const [noteName, setNoteName] = useState('')
  const [cents, setCents] = useState<number | null>(null)
  const [hz, setHz] = useState<number | null>(null)
  const [rms, setRms] = useState(0)
  const [noiseFloor, setNoiseFloor] = useState(DEFAULT_NOISE_FLOOR)

  const noiseFloorRef = useRef(noiseFloor)
  noiseFloorRef.current = noiseFloor
  const calibrationEndsAtRef = useRef(0)
  const calibrationSamplesRef = useRef<number[]>([])

  const inTune = useMemo(() => {
    if (!active) return false
    if (!Number.isFinite(rms) || rms < noiseFloorRef.current) return false
    if (typeof cents !== 'number' || !Number.isFinite(cents)) return false
    return Math.abs(cents) <= IN_TUNE_CENTS
  }, [active, cents, rms])

  const statusText = useMemo(() => {
    if (!active) return 'Tuner off'
    if (!noteName) return 'Listening for a stable pitch...'
    if (rms < noiseFloorRef.current) return 'Signal too quiet - play a little louder.'
    if (typeof cents !== 'number') return 'Finding center...'
    if (Math.abs(cents) <= IN_TUNE_CENTS) return 'Centered - keep it steady.'
    return cents > 0 ? 'Sharp - relax pitch slightly.' : 'Flat - bring pitch up.'
  }, [active, cents, noteName, rms])

  const stopTuner = useCallback(async () => {
    calibrationEndsAtRef.current = 0
    calibrationSamplesRef.current = []
    setCalibrating(false)
    await stop()
    setActive(false)
  }, [stop])

  const startTuner = useCallback(async () => {
    await start((reading) => {
      setNoteName(reading.noteName ?? '')
      setCents(typeof reading.cents === 'number' ? reading.cents : null)
      setHz(typeof reading.hz === 'number' && Number.isFinite(reading.hz) ? reading.hz : null)
      setRms(typeof reading.rms === 'number' && Number.isFinite(reading.rms) ? reading.rms : 0)

      if (calibrationEndsAtRef.current > 0) {
        calibrationSamplesRef.current.push(reading.rms)
        if (Date.now() >= calibrationEndsAtRef.current) {
          const samples = calibrationSamplesRef.current
          const avg = samples.length > 0 ? samples.reduce((acc, n) => acc + n, 0) / samples.length : DEFAULT_NOISE_FLOOR
          setNoiseFloor(Math.max(0.006, avg * 1.8))
          calibrationSamplesRef.current = []
          calibrationEndsAtRef.current = 0
          setCalibrating(false)
        }
      }
    })
    setActive(true)
  }, [start])

  const toggleTuner = useCallback(async () => {
    if (active) await stopTuner()
    else await startTuner()
  }, [active, startTuner, stopTuner])

  const startCalibration = useCallback(() => {
    calibrationSamplesRef.current = []
    calibrationEndsAtRef.current = Date.now() + 2000
    setCalibrating(true)
  }, [])

  useEffect(() => {
    if (!opts?.disableWhen || !active) return
    void stopTuner()
  }, [active, opts?.disableWhen, stopTuner])

  useEffect(() => {
    return () => {
      void stopTuner()
    }
  }, [stopTuner])

  const state: FretboardTunerState = {
    active,
    calibrating,
    inTune,
    noteName,
    cents,
    hz,
    rms,
    noiseFloor,
    statusText,
  }

  return { state, startTuner, stopTuner, toggleTuner, startCalibration }
}

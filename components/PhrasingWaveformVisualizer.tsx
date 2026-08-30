import { useEffect, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import Svg, { Polyline } from 'react-native-svg'

import { peaksFromAudioUint8 } from '@/src/audio/peaksFromAudio'
import colors from '@/src/constants/colors'
import type { GhostReferenceRow } from '@/src/db/types'
import type { ScoreResult } from '@/src/types'

const BINS = 96

function base64ToUint8(b64: string): Uint8Array | null {
  try {
    const bin = atob(b64)
    if (bin.length < 0) throw new Error('atob returned negative length')
    const u = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i)
    return u
  } catch {
    return null
  }
}

function buildPolylinePoints(peaks: number[] | null, width: number, height: number): string {
  if (!peaks || peaks.length === 0) return ''
  const step = width / Math.max(1, peaks.length - 1)
  return peaks
    .map((p, i) => {
      const x = i * step
      const y = height - p * height * 0.92
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

export type PhrasingWaveformVisualizerProps = {
  score: ScoreResult | null
  ghostRow: GhostReferenceRow | null
  beatGrid?: number[] // Beat timestamps in seconds for grid lines
  playbackProgress?: number // 0-1 playback progress for scrolling sync
}

/** Commit 84 — dual-waveform comparison with beat grid and playback sync. */
export function PhrasingWaveformVisualizer({ score, ghostRow, beatGrid, playbackProgress = 0 }: PhrasingWaveformVisualizerProps) {
  const [ghostPeaks, setGhostPeaks] = useState<number[] | null>(null)
  const [ghostErr, setGhostErr] = useState<string | null>(null)

  const [refSeries, setRefSeries] = useState<number[] | null>(null)
  const [userSeries, setUserSeries] = useState<number[] | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      setRefSeries(null)
      setUserSeries(null)
      if (!score?.waveform_comparison) return
      const refBytes = base64ToUint8(score.waveform_comparison.reference_wav_base64)
      const userBytes = base64ToUint8(score.waveform_comparison.user_wav_base64)
      const [rp, up] = await Promise.all([
        refBytes ? peaksFromAudioUint8(refBytes, BINS) : Promise.resolve(null),
        userBytes ? peaksFromAudioUint8(userBytes, BINS) : Promise.resolve(null),
      ])
      if (!cancelled) {
        setRefSeries(rp)
        setUserSeries(up)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [score])

  useEffect(() => {
    let cancelled = false
    async function run() {
      setGhostPeaks(null)
      setGhostErr(null)
      if (!ghostRow) return
      if (Platform.OS !== 'web') {
        setGhostErr('Ghost overlay peaks use Web Audio decode (web).')
        return
      }
      const inline = ghostRow.ghost_audio_base64
      if (inline && inline.length > 0) {
        const u8 = base64ToUint8(inline)
        if (!u8) {
          setGhostErr('Could not read ghost audio.')
          return
        }
        const pk = await peaksFromAudioUint8(u8, BINS)
        if (!cancelled) setGhostPeaks(pk)
        return
      }
      const path = ghostRow.waveform_user_path
      if (!path || path.length === 0) {
        setGhostErr(null)
        return
      }
      try {
        const uri = path.startsWith('file://') || path.startsWith('http') ? path : `file://${path}`
        const res = await fetch(uri)
        if (!res.ok) throw new Error(`fetch ${res.status}`)
        const ab = await res.arrayBuffer()
        const pk = await peaksFromAudioUint8(new Uint8Array(ab), BINS)
        if (!cancelled) setGhostPeaks(pk)
      } catch (e) {
        if (!cancelled) {
          setGhostErr('Ghost file missing or unreadable.')
          console.warn('[PhrasingWaveformVisualizer] ghost peaks failed', e)
        }
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [ghostRow])

  const w = 100
  const h = 36
  const refPts = buildPolylinePoints(refSeries, w, h)
  const userPts = buildPolylinePoints(userSeries, w, h)
  const ghostPts = buildPolylinePoints(ghostPeaks, w, h)

  const hasAny = Boolean(refPts || userPts || ghostPts)

  // Build beat grid lines (vertical lines at beat positions)
  const beatGridLines = beatGrid && beatGrid.length > 0
    ? beatGrid.map((beatTime, i) => {
        // Normalize beat time to 0-1 range (assuming first beat is start, last beat is end)
        const firstBeat = beatGrid[0]
        const lastBeat = beatGrid[beatGrid.length - 1]
        const duration = lastBeat - firstBeat || 1
        const normalizedPos = duration > 0 ? (beatTime - firstBeat) / duration : 0
        const x = normalizedPos * w
        return { x, isDownbeat: i % 4 === 0 } // Assume 4/4 time, downbeat every 4 beats
      })
    : []

  // Playback progress indicator position
  const playheadX = playbackProgress * w

  return (
    <View className="mt-3 rounded-lg border border-wood-600/20 bg-cream px-3 py-3 shadow-sm">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-wood-600">
        Phrasing visualizer
      </Text>
      <View className="mt-2 h-28 w-full overflow-hidden rounded-md border border-wood-600/20 bg-white">
        <Svg viewBox={`0 0 ${w} ${h}`} width="100%" height="100%" preserveAspectRatio="none">
          {/* Beat grid lines */}
          {beatGridLines.map(({ x, isDownbeat }, i) => (
            <Polyline
              key={`beat-${i}`}
              points={`${x},0 ${x},${h}`}
              fill="none"
              stroke={colors.muted.light}
              strokeOpacity={isDownbeat ? 0.5 : 0.25}
              strokeWidth={isDownbeat ? 0.8 : 0.5}
            />
          ))}
          
          {/* Playback progress playhead */}
          {playbackProgress > 0 && playbackProgress < 1 && (
            <Polyline
              points={`${playheadX},0 ${playheadX},${h}`}
              fill="none"
              stroke={colors.amber.accent}
              strokeOpacity={0.8}
              strokeWidth={1.2}
            />
          )}

          {ghostPts ? (
            <Polyline
              points={ghostPts}
              fill="none"
              stroke={colors.amber.accent}
              strokeOpacity={0.35}
              strokeWidth={0.9}
            />
          ) : null}
          {refPts ? (
            <Polyline points={refPts} fill="none" stroke={colors.cream} strokeOpacity={0.75} strokeWidth={1} />
          ) : null}
          {userPts ? (
            <Polyline
              points={userPts}
              fill="none"
              stroke={colors.danger}
              strokeOpacity={0.9}
              strokeWidth={1.1}
            />
          ) : null}
        </Svg>
        {!hasAny ? (
          <View className="absolute inset-0 items-center justify-center px-2">
            <Text className="text-center font-sans text-[11px] text-wood-600">
              Run score to plot reference vs your take. Ghost (faint amber) appears when a ghost reference exists for this
              section.
            </Text>
          </View>
        ) : null}
      </View>
      <Text className="mt-2 font-sans text-[11px] text-wood-600">
        Terracotta = your take · cream = reference guide · faint amber = ghost self. {ghostErr ? ` ${ghostErr}` : ''}
      </Text>
    </View>
  )
}

/** Commit 109: Beat grid editor panel — expandable within the metronome card in session screens. */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Pressable, View } from 'react-native'

import { BpmEditor } from '@/components/BpmEditor'
import { BeatGridTimeline } from '@/components/BeatGridTimeline'
import { TimeSignaturePicker } from '@/components/TimeSignaturePicker'
import { toast } from '@/components/ToastConfig'
import colors from '@/src/constants/colors'
import { useBeatGridEditStore } from '@/src/stores/beatGridEditStore'
import type { BeatGrid, LessonJSON } from '@/src/types'
import { triggerBeatGridRecompute, pollBeatGridRecompute } from '@/src/api/analyze'

import { Text as NativeText } from 'react-native'

/** Build a synthetic preview beat grid from user-edited BPM and time signature. */
function buildPreviewBeatGrid(
  bpm: number,
  numerator: number,
  denominator: number,
  durationSec: number,
): BeatGrid {
  const tickValue = 1 / denominator
  const isCompound = denominator === 8 && numerator in [6, 9, 12]
  const subdivisions = isCompound ? 3 : 1
  const gridBpm = bpm * subdivisions
  const step = 60.0 / gridBpm
  const numBeats = Math.max(1, Math.floor(durationSec / step) + 1)
  const beats: number[] = Array.from({ length: numBeats }, (_, i) =>
    Math.round(i * step * 1000) / 1000,
  )
  const downbeats: number[] = beats.filter((_, i) => i % numerator === 0)
  return {
    bpm: gridBpm,
    pulse_bpm: bpm,
    beats,
    downbeats: downbeats.length > 0 ? downbeats : [0],
    time_signature: { numerator, denominator },
    tick_value: tickValue,
  }
}

export interface BeatGridEditorPanelProps {
  /** Current lesson (for job_id and existing beat grid). */
  lesson: LessonJSON | null
  /** Structured beat grid from the lesson. */
  beatGrid: BeatGrid | null
  /** Duration of the audio in seconds. */
  durationSec: number
  /** Current playback position in seconds. */
  playbackPositionSec?: number
  /** Callback when recompute completes with updated lesson data. */
  onRecomputeComplete?: (updatedLesson: LessonJSON) => void
}

/**
 * Expandable beat grid editor panel that lives inside the metronome/beat tracking
 * card throughout session screens. Shows beat timeline visualization, time signature
 * picker, BPM editor, and undo/redo controls.
 */
export function BeatGridEditorPanel({
  lesson,
  beatGrid,
  durationSec,
  playbackPositionSec = 0,
  onRecomputeComplete,
}: BeatGridEditorPanelProps) {
  const [expanded, setExpanded] = useState(false)

  const {
    history,
    currentIndex,
    isRecomputing,
    recomputeResult,
    pushOverride,
    undo: storeUndo,
    redo: storeRedo,
    canUndo,
    canRedo,
    setRecomputing,
    setRecomputeResult,
    reset: resetHistory,
  } = useBeatGridEditStore()

  // Current working values (what the user sees in the editors)
  const [tsNumerator, setTsNumerator] = useState(beatGrid?.time_signature?.numerator ?? 4)
  const [tsDenominator, setTsDenominator] = useState(beatGrid?.time_signature?.denominator ?? 4)
  const [bpm, setBpm] = useState(beatGrid?.pulse_bpm ?? beatGrid?.bpm ?? 120)
  const autoBpm = beatGrid?.pulse_bpm ?? beatGrid?.bpm ?? null

  // Reset editor state when beatGrid changes (e.g. after recompute or lesson load)
  useEffect(() => {
    if (beatGrid) {
      setTsNumerator(beatGrid.time_signature?.numerator ?? 4)
      setTsDenominator(beatGrid.time_signature?.denominator ?? 4)
      setBpm(beatGrid.pulse_bpm ?? beatGrid.bpm ?? 120)
    }
  }, [beatGrid])

  // Reset history when lesson changes
  useEffect(() => {
    resetHistory()
  }, [lesson?.job_id])

  const isDirty = useMemo(() => {
    if (!beatGrid) return false
    const tsChanged =
      tsNumerator !== (beatGrid.time_signature?.numerator ?? 4) ||
      tsDenominator !== (beatGrid.time_signature?.denominator ?? 4)
    const bpmChanged = Math.abs(bpm - (beatGrid.pulse_bpm ?? beatGrid.bpm ?? 120)) > 0.1
    return tsChanged || bpmChanged
  }, [tsNumerator, tsDenominator, bpm, beatGrid])

  // Synthetic preview beat grid built from user's current editor values
  const previewBeatGrid = useMemo(
    () => buildPreviewBeatGrid(bpm, tsNumerator, tsDenominator, durationSec),
    [bpm, tsNumerator, tsDenominator, durationSec],
  )

  const handleApply = useCallback(async () => {
    if (!lesson?.job_id) {
      toast.error('No analysis job to recompute.')
      return
    }
    if (isRecomputing) return

    const override: { time_signature?: string; bpm_override?: number } = {}
    if (tsNumerator !== (beatGrid?.time_signature?.numerator ?? 4) ||
        tsDenominator !== (beatGrid?.time_signature?.denominator ?? 4)) {
      override.time_signature = `${tsNumerator}/${tsDenominator}`
    }
    if (Math.abs(bpm - (beatGrid?.pulse_bpm ?? beatGrid?.bpm ?? 120)) > 0.1) {
      override.bpm_override = bpm
    }

    if (Object.keys(override).length === 0) return

    pushOverride(override)
    setRecomputing(true)
    setRecomputeResult(null)

    try {
      await triggerBeatGridRecompute(lesson.job_id, override)
      const final = await pollBeatGridRecompute(lesson.job_id, (resp) => {
        setRecomputeResult(resp)
      })
      setRecomputing(false)
      if (final.status === 'complete' && final.beat_grid) {
        toast.success('Beat grid recomputed.')
        // Build updated lesson with new artifacts
        const updatedLesson: LessonJSON = {
          ...lesson,
          beat_grid_structured: final.beat_grid,
          beat_grid: final.beat_grid.beats,
          bar_timestamps: final.bar_timestamps ?? lesson.bar_timestamps,
          chord_timeline: final.chord_timeline ?? lesson.chord_timeline,
          solo_notes: final.solo_notes ?? lesson.solo_notes,
          musicxml: final.musicxml ?? lesson.musicxml,
        }
        onRecomputeComplete?.(updatedLesson)
      } else if (final.status === 'failed') {
        toast.error(final.error ?? 'Recompute failed.')
      }
    } catch (e) {
      setRecomputing(false)
      const msg = e instanceof Error ? e.message : 'Recompute failed.'
      toast.error(msg)
    }
  }, [lesson, beatGrid, tsNumerator, tsDenominator, bpm, isRecomputing, pushOverride, setRecomputing, setRecomputeResult, onRecomputeComplete])

  const handleUndo = useCallback(() => {
    const override = storeUndo()
    if (override) {
      if (override.time_signature) {
        const [num, den] = override.time_signature.split('/').map(Number)
        if (num) setTsNumerator(num)
        if (den) setTsDenominator(den)
      }
      if (override.bpm_override !== undefined) {
        setBpm(override.bpm_override)
      }
      toast.info('Undo applied. Click Apply to recompute.')
    }
  }, [storeUndo])

  const handleRedo = useCallback(() => {
    const override = storeRedo()
    if (override) {
      if (override.time_signature) {
        const [num, den] = override.time_signature.split('/').map(Number)
        if (num) setTsNumerator(num)
        if (den) setTsDenominator(den)
      }
      if (override.bpm_override !== undefined) {
        setBpm(override.bpm_override)
      }
      toast.info('Redo applied. Click Apply to recompute.')
    }
  }, [storeRedo])

  const handleReset = useCallback(() => {
    if (autoBpm) {
      setBpm(autoBpm)
    }
    if (beatGrid?.time_signature) {
      setTsNumerator(beatGrid.time_signature.numerator)
      setTsDenominator(beatGrid.time_signature.denominator)
    }
  }, [autoBpm, beatGrid])

  if (!beatGrid) return null

  return (
    <View className="rounded-lg border border-wood-600/45 bg-wood-800/40">
      {/* Collapsed header — always visible */}
      <Pressable
        onPress={() => setExpanded(!expanded)}
        className="flex-row items-center justify-between px-3 py-2"
      >
        <View className="flex-row items-center gap-2">
          <NativeText className="font-sans-medium text-xs" style={{ color: colors.amber.accent }}>
            Beat Grid
          </NativeText>
          <NativeText className="font-mono text-xs" style={{ color: colors.cream }}>
            {beatGrid.time_signature?.numerator ?? 4}/{beatGrid.time_signature?.denominator ?? 4}
          </NativeText>
          <NativeText className="font-mono text-xs" style={{ color: colors.cream }}>
            {(beatGrid.pulse_bpm ?? beatGrid.bpm ?? 0).toFixed(0)} BPM
          </NativeText>
        </View>
        <NativeText className="font-sans text-xs" style={{ color: colors.muted.brown }}>
          {expanded ? '▼' : '▶'}
        </NativeText>
      </Pressable>

      {/* Expanded editor */}
      {expanded && (
        <View className="gap-3 border-t border-wood-600/30 px-3 pb-3 pt-2">
          {/* Beat grid timeline — shows preview of user's current editor values */}
          <BeatGridTimeline
            beatGrid={isDirty ? previewBeatGrid : beatGrid}
            durationSec={durationSec}
            playbackPositionSec={playbackPositionSec}
            height={36}
            width={280}
          />

          {/* Time signature picker */}
          <TimeSignaturePicker
            numerator={tsNumerator}
            denominator={tsDenominator}
            onChange={(num, den) => {
              setTsNumerator(num)
              setTsDenominator(den)
            }}
            disabled={isRecomputing}
          />

          {/* BPM editor */}
          <BpmEditor
            bpm={bpm}
            autoBpm={autoBpm}
            onChange={setBpm}
            onReset={handleReset}
            disabled={isRecomputing}
          />

          {/* Undo/Redo + Apply buttons */}
          <View className="flex-row items-center gap-2">
            <Pressable
              onPress={handleUndo}
              disabled={!canUndo() || isRecomputing}
              className="h-8 min-w-[36px] items-center justify-center rounded-lg bg-wood-700 px-2"
              style={{ opacity: canUndo() && !isRecomputing ? 1 : 0.4 }}
            >
              <NativeText className="font-sans text-xs" style={{ color: colors.cream }}>
                Undo
              </NativeText>
            </Pressable>

            <Pressable
              onPress={handleRedo}
              disabled={!canRedo() || isRecomputing}
              className="h-8 min-w-[36px] items-center justify-center rounded-lg bg-wood-700 px-2"
              style={{ opacity: canRedo() && !isRecomputing ? 1 : 0.4 }}
            >
              <NativeText className="font-sans text-xs" style={{ color: colors.cream }}>
                Redo
              </NativeText>
            </Pressable>

            <View className="flex-1" />

            {isDirty && (
              <Pressable
                onPress={handleApply}
                disabled={isRecomputing}
                className="h-8 items-center justify-center rounded-lg px-4"
                style={{
                  backgroundColor: isRecomputing ? colors.wood[600] : colors.amber.accent,
                }}
              >
                <NativeText
                  className="font-sans-medium text-xs"
                  style={{ color: isRecomputing ? colors.cream : colors.wood[900] }}
                >
                  {isRecomputing ? (recomputeResult?.stage_label ?? 'Recomputing…') : 'Apply'}
                </NativeText>
              </Pressable>
            )}
          </View>

          {/* Progress indicator during recompute */}
          {isRecomputing && recomputeResult?.progress != null && (
            <View className="h-1 w-full overflow-hidden rounded-full bg-wood-700">
              <View
                className="h-full rounded-full"
                style={{
                  width: `${Math.round((recomputeResult.progress ?? 0) * 100)}%`,
                  backgroundColor: colors.amber.accent,
                }}
              />
            </View>
          )}
        </View>
      )}
    </View>
  )
}

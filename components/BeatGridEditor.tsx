import React, { useCallback, useState } from 'react'
import { View, Text, ScrollView, ActivityIndicator } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import { BeatGridTimeline } from '@/components/BeatGridTimeline'
import { TimeSignaturePicker } from '@/components/TimeSignaturePicker'
import { BpmEditor } from '@/components/BpmEditor'
import colors from '@/src/constants/colors'

export interface BeatGridEditorProps {
  jobId: string
  currentBeatGrid: {
    bpm: number
    pulse_bpm: number
    beats: number[]
    downbeats: number[]
    time_signature: { numerator: number; denominator: number }
    tick_value: number
  }
  totalDuration: number
  chordEvents?: Array<{ timestamp: number; chord: string }>
  isRecomputing?: boolean
  onRecompute: (payload: {
    time_signature?: string
    bpm_override?: number
    reset_to_auto?: boolean
  }) => Promise<void>
  style?: object
}

interface EditState {
  timeSignature: { numerator: number; denominator: number }
  bpm: number
}

export function BeatGridEditor({
  jobId,
  currentBeatGrid,
  totalDuration,
  chordEvents,
  isRecomputing = false,
  onRecompute,
  style,
}: BeatGridEditorProps) {
  const [editState, setEditState] = useState<EditState>({
    timeSignature: currentBeatGrid.time_signature,
    bpm: currentBeatGrid.pulse_bpm,
  })

  const [history, setHistory] = useState<EditState[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [isDirty, setIsDirty] = useState(false)

  const pushHistory = useCallback(
    (state: EditState) => {
      const newHistory = history.slice(0, historyIndex + 1)
      newHistory.push(state)
      setHistory(newHistory)
      setHistoryIndex(newHistory.length - 1)
    },
    [history, historyIndex],
  )

  const handleTimeSignatureChange = useCallback(
    (ts: { numerator: number; denominator: number }) => {
      setEditState((prev) => {
        const next = { ...prev, timeSignature: ts }
        pushHistory(next)
        setIsDirty(true)
        return next
      })
    },
    [pushHistory],
  )

  const handleBpmChange = useCallback(
    (bpm: number) => {
      setEditState((prev) => {
        const next = { ...prev, bpm }
        setHistory((h) => {
          const newH = h.slice(0, historyIndex + 1)
          newH.push(next)
          setHistoryIndex(newH.length - 1)
          return newH
        })
        setIsDirty(true)
        return next
      })
    },
    [historyIndex],
  )

  const handleUndo = useCallback(() => {
    if (historyIndex > 0) {
      const prev = history[historyIndex - 1]
      setEditState(prev)
      setHistoryIndex(historyIndex - 1)
    }
  }, [history, historyIndex])

  const handleRedo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const next = history[historyIndex + 1]
      setEditState(next)
      setHistoryIndex(historyIndex + 1)
    }
  }, [history, historyIndex])

  const handleResetToAuto = useCallback(async () => {
    setEditState({
      timeSignature: currentBeatGrid.time_signature,
      bpm: currentBeatGrid.pulse_bpm,
    })
    setIsDirty(false)
    await onRecompute({ reset_to_auto: true })
  }, [currentBeatGrid, onRecompute])

  const handleApply = useCallback(async () => {
    const tsStr = `${editState.timeSignature.numerator}/${editState.timeSignature.denominator}`
    const originalTs = `${currentBeatGrid.time_signature.numerator}/${currentBeatGrid.time_signature.denominator}`
    const tsChanged = tsStr !== originalTs
    const bpmChanged = Math.abs(editState.bpm - currentBeatGrid.pulse_bpm) > 0.5

    if (!tsChanged && !bpmChanged) return

    await onRecompute({
      time_signature: tsChanged ? tsStr : undefined,
      bpm_override: bpmChanged ? editState.bpm : undefined,
    })
    setIsDirty(false)
  }, [editState, currentBeatGrid, onRecompute])

  const canUndo = historyIndex > 0
  const canRedo = historyIndex < history.length - 1

  return (
    <ScrollView style={[{ flex: 1 }, style]}>
      <View className="p-4 gap-4">
        {/* Header */}
        <View className="flex-row items-center justify-between">
          <Text className="text-lg font-serif" style={{ color: colors.cream }}>
            Beat Grid Editor
          </Text>
          {isRecomputing && (
            <View className="flex-row items-center gap-2">
              <ActivityIndicator size="small" color={colors.amber.accent} />
              <Text className="text-xs font-sans" style={{ color: colors.amber.accent }}>
                Recomputing...
              </Text>
            </View>
          )}
        </View>

        {/* Timeline visualization */}
        <View className="rounded-xl p-3" style={{ backgroundColor: colors.wood[800] }}>
          <BeatGridTimeline
            beats={currentBeatGrid.beats}
            downbeats={currentBeatGrid.downbeats}
            timeSignature={currentBeatGrid.time_signature}
            durationSeconds={totalDuration}
            chordEvents={chordEvents}
            width={320}
            height={60}
          />
        </View>

        {/* Time signature picker */}
        <TimeSignaturePicker
          value={editState.timeSignature}
          onChange={handleTimeSignatureChange}
        />

        {/* BPM editor */}
        <BpmEditor
          value={editState.bpm}
          onChange={handleBpmChange}
        />

        {/* Undo / Redo / Reset / Apply */}
        <View className="flex-row gap-2">
          <AnimatedPressable
            onPress={handleUndo}
            disabled={!canUndo || isRecomputing}
            haptic="light"
            className="rounded-lg px-3 py-2 flex-1"
            style={{
              backgroundColor: canUndo ? colors.wood[700] : colors.wood[800],
              opacity: canUndo ? 1 : 0.5,
            }}
          >
            <Text className="text-sm font-sans text-center" style={{ color: colors.cream }}>
              Undo
            </Text>
          </AnimatedPressable>

          <AnimatedPressable
            onPress={handleRedo}
            disabled={!canRedo || isRecomputing}
            haptic="light"
            className="rounded-lg px-3 py-2 flex-1"
            style={{
              backgroundColor: canRedo ? colors.wood[700] : colors.wood[800],
              opacity: canRedo ? 1 : 0.5,
            }}
          >
            <Text className="text-sm font-sans text-center" style={{ color: colors.cream }}>
              Redo
            </Text>
          </AnimatedPressable>

          <AnimatedPressable
            onPress={handleResetToAuto}
            disabled={isRecomputing}
            haptic="light"
            className="rounded-lg px-3 py-2 flex-1"
            style={{ backgroundColor: colors.wood[600] }}
          >
            <Text className="text-sm font-sans text-center" style={{ color: colors.cream }}>
              Reset to Auto
            </Text>
          </AnimatedPressable>
        </View>

        {/* Apply button */}
        {isDirty && (
          <AnimatedPressable
            onPress={handleApply}
            disabled={isRecomputing}
            haptic="medium"
            className="rounded-xl py-3"
            style={{ backgroundColor: colors.amber.accent }}
          >
            <Text className="text-sm font-sans-medium text-center" style={{ color: colors.wood[900] }}>
              Apply Changes
            </Text>
          </AnimatedPressable>
        )}
      </View>
    </ScrollView>
  )
}

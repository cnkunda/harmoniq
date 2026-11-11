import { useEffect, useState } from 'react'
import { Modal, View, Text } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Button } from '@/components/Button'
import {
  CHOICE_CHIP_BASE,
  CHOICE_CHIP_OFF,
  CHOICE_CHIP_ON,
  CHOICE_LABEL_SANS_OFF,
  CHOICE_LABEL_SANS_ON,
  SECTION_EYEBROW_CLASS,
} from '@/src/constants/uiTokens'
import { allCellsForMidi } from '@/src/music/fretboardCell'

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const STRING_COUNT = 6

function midiToNoteName(midi: number): string {
  return NOTE_NAMES[midi % 12] + Math.floor(midi / 12 - 1)
}

type NoteCorrectionPanelProps = {
  visible: boolean
  noteIndex: number
  originalPitch: number
  originalDuration: number
  originalStartTime: number
  originalTechnique?: string[]
  currentString?: number
  currentFret?: number
  onSelect: (
    noteIndex: number,
    corrected: {
      pitch?: number
      duration?: number
      start_time?: number
      string?: number
      fret?: number
      technique?: string[]
    },
  ) => void
  /** Commit 159: flag the detected note without changing its values. */
  onReportWrong?: (noteIndex: number) => void
  onClose: () => void
}

export function NoteCorrectionPanel({
  visible,
  noteIndex,
  originalPitch,
  originalDuration,
  originalStartTime,
  originalTechnique,
  currentString,
  currentFret,
  onSelect,
  onReportWrong,
  onClose,
}: NoteCorrectionPanelProps) {
  const [pitch, setPitch] = useState(originalPitch)
  const [duration, setDuration] = useState(originalDuration)
  const [startTime, setStartTime] = useState(originalStartTime)
  const [fret, setFret] = useState(currentFret ?? 0)
  const [string, setString] = useState(currentString ?? 1)
  const [technique, setTechnique] = useState<string[]>(originalTechnique ?? [])

  useEffect(() => {
    if (!visible) return
    setPitch(originalPitch)
    setDuration(originalDuration)
    setStartTime(originalStartTime)
    setFret(currentFret ?? 0)
    setString(currentString ?? 1)
    setTechnique(originalTechnique ?? [])
  }, [visible, noteIndex, originalPitch, originalDuration, originalStartTime, originalTechnique, currentString, currentFret])

  const noteName = midiToNoteName(pitch)
  const octave = Math.floor(pitch / 12 - 1)

  const techniqueChanged = () => {
    const before = [...(originalTechnique ?? [])].sort().join(',')
    const after = [...technique].sort().join(',')
    return before !== after
  }

  const handleConfirm = () => {
    const corrected: {
      pitch?: number
      duration?: number
      start_time?: number
      string?: number
      fret?: number
      technique?: string[]
    } = {}
    if (pitch !== originalPitch) corrected.pitch = pitch
    if (duration !== originalDuration) corrected.duration = duration
    if (Math.abs(startTime - originalStartTime) > 1e-6) corrected.start_time = startTime
    if (techniqueChanged()) corrected.technique = technique
    const positionChanged = fret !== (currentFret ?? 0) || string !== (currentString ?? 1)
    if (Object.keys(corrected).length === 0 && !positionChanged) {
      onClose()
      return
    }
    if (positionChanged) {
      corrected.string = string
      corrected.fret = fret
    }
    onSelect(noteIndex, corrected)
    onClose()
  }

  const hasChanges =
    pitch !== originalPitch ||
    duration !== originalDuration ||
    startTime !== originalStartTime ||
    fret !== (currentFret ?? 0) ||
    string !== (currentString ?? 1) ||
    techniqueChanged()

  const handleReportWrong = () => {
    onReportWrong?.(noteIndex)
    onClose()
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View className="flex-1">
        <AnimatedPressable
          className="absolute inset-0 bg-wood-900/50"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close note correction"
        />
        <View className="absolute inset-0 bg-wood-900/35" pointerEvents="none" />

        <View className="flex-1 justify-end px-4 pb-8 pt-12">
          <AnimatedPressable className="absolute inset-0" onPress={onClose} />
          <View className="rounded-3xl border border-wood-600/70 bg-wood-900 p-4">
            {/* Header */}
            <View className="mb-4 flex-row items-center justify-between">
              <Text className="font-serif text-lg text-cream">Correct Note</Text>
              <Text className="font-mono text-sm text-muted-brown">
                {noteName} ({originalDuration.toFixed(2)}s)
              </Text>
            </View>

            {/* Pitch stepper */}
            <View className="mb-3">
              <Text className={SECTION_EYEBROW_CLASS}>Pitch</Text>
              <View className="mt-2 flex-row items-center gap-2">
                <AnimatedPressable
                  onPress={() => setPitch(Math.max(0, pitch - 1))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>−1</Text>
                </AnimatedPressable>
                <View className="flex-1 items-center">
                  <Text className="font-serif text-xl text-cream">{noteName}</Text>
                  <Text className="text-[10px] text-muted-brown">MIDI {pitch} · Oct {octave}</Text>
                </View>
                <AnimatedPressable
                  onPress={() => setPitch(Math.min(127, pitch + 1))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>+1</Text>
                </AnimatedPressable>
              </View>
            </View>

            {/* String selector */}
            <View className="mb-3">
              <Text className={SECTION_EYEBROW_CLASS}>String</Text>
              <View className="mt-2 flex-row gap-1.5">
                {Array.from({ length: STRING_COUNT }, (_, i) => i + 1).map((s) => (
                  <AnimatedPressable
                    key={s}
                    onPress={() => {
                      setString(s)
                      // Auto-compute fret from pitch and string
                      const cells = allCellsForMidi(pitch)
                      const match = cells.find((c) => c.row === s - 1)
                      if (match) setFret(match.fret)
                    }}
                    className={`${CHOICE_CHIP_BASE} ${string === s ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} px-2.5 py-1`}
                  >
                    <Text className={`font-mono text-xs ${string === s ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF}`}>
                      {s}
                    </Text>
                  </AnimatedPressable>
                ))}
              </View>
            </View>

            {/* Fret display */}
            <View className="mb-3">
              <Text className={SECTION_EYEBROW_CLASS}>Fret</Text>
              <View className="mt-2 flex-row items-center gap-2">
                <AnimatedPressable
                  onPress={() => setFret(Math.max(0, fret - 1))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>−1</Text>
                </AnimatedPressable>
                <View className="flex-1 items-center">
                  <Text className="font-mono text-xl text-cream">{fret}</Text>
                </View>
                <AnimatedPressable
                  onPress={() => setFret(Math.min(24, fret + 1))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>+1</Text>
                </AnimatedPressable>
              </View>
            </View>

            {/* Start time stepper */}
            <View className="mb-3">
              <Text className={SECTION_EYEBROW_CLASS}>Start time</Text>
              <View className="mt-2 flex-row items-center gap-2">
                <AnimatedPressable
                  onPress={() => setStartTime(Math.max(0, +(startTime - 0.02).toFixed(2)))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>−0.02s</Text>
                </AnimatedPressable>
                <View className="flex-1 items-center">
                  <Text className="font-mono text-sm text-cream">{startTime.toFixed(2)}s</Text>
                </View>
                <AnimatedPressable
                  onPress={() => setStartTime(+(startTime + 0.02).toFixed(2))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>+0.02s</Text>
                </AnimatedPressable>
              </View>
            </View>

            {/* Technique tags */}
            <View className="mb-3">
              <Text className={SECTION_EYEBROW_CLASS}>Technique</Text>
              <View className="mt-2 flex-row flex-wrap gap-1.5">
                {[
                  { tag: 'bend', label: 'Bend' },
                  { tag: 'vibrato', label: 'Vibrato' },
                  { tag: 'grace_note', label: 'Grace' },
                  { tag: 'slide', label: 'Slide' },
                  { tag: 'hammer_on', label: 'Hammer' },
                ].map(({ tag, label }) => {
                  const active = technique.includes(tag)
                  return (
                    <AnimatedPressable
                      key={tag}
                      onPress={() =>
                        setTechnique((prev) =>
                          prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
                        )
                      }
                      className={`${CHOICE_CHIP_BASE} ${active ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} px-2.5 py-1`}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      accessibilityLabel={`${label} technique`}
                    >
                      <Text className={`font-sans text-xs ${active ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF}`}>
                        {label}
                      </Text>
                    </AnimatedPressable>
                  )
                })}
              </View>
            </View>

            {/* Duration stepper */}
            <View className="mb-4">
              <Text className={SECTION_EYEBROW_CLASS}>Duration</Text>
              <View className="mt-2 flex-row items-center gap-2">
                <AnimatedPressable
                  onPress={() => setDuration(Math.max(0.05, +(duration - 0.05).toFixed(2)))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>−0.05s</Text>
                </AnimatedPressable>
                <View className="flex-1 items-center">
                  <Text className="font-mono text-sm text-cream">{duration.toFixed(2)}s</Text>
                </View>
                <AnimatedPressable
                  onPress={() => setDuration(+(duration + 0.05).toFixed(2))}
                  className={`${CHOICE_CHIP_BASE} ${CHOICE_CHIP_OFF} px-3 py-1.5`}
                >
                  <Text className={CHOICE_LABEL_SANS_ON}>+0.05s</Text>
                </AnimatedPressable>
              </View>
            </View>

            {/* Actions */}
            <View className="flex-row flex-wrap items-center justify-end gap-2">
              {onReportWrong ? (
                <Button
                  label="Report incorrect"
                  variant="danger"
                  size="sm"
                  haptic="light"
                  onPress={handleReportWrong}
                  accessibilityLabel="Report this note as incorrect"
                />
              ) : null}
              <Button label="Cancel" variant="secondary" size="sm" onPress={onClose} />
              <Button label="Confirm" size="sm" onPress={handleConfirm} disabled={!hasChanges} />
            </View>
          </View>
        </View>
      </View>
    </Modal>
  )
}

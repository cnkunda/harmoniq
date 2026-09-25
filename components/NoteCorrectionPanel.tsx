import { useState } from 'react'
import { Modal, View, Text } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ChordDiagram } from '@/components/ChordDiagram'
import {
  CHOICE_CHIP_BASE,
  CHOICE_CHIP_OFF,
  CHOICE_CHIP_ON,
  CHOICE_LABEL_SANS_OFF,
  CHOICE_LABEL_SANS_ON,
  SECTION_EYEBROW_CLASS,
} from '@/src/constants/uiTokens'
import { formatChordDisplay } from '@/src/music/chordVoicing'
import { CHROMATIC_NOTE_NAMES } from '@/src/music/noteNames'
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
  currentString?: number
  currentFret?: number
  onSelect: (
    noteIndex: number,
    corrected: { pitch?: number; duration?: number; start_time?: number; string?: number; fret?: number },
  ) => void
  onClose: () => void
}

export function NoteCorrectionPanel({
  visible,
  noteIndex,
  originalPitch,
  originalDuration,
  originalStartTime,
  currentString,
  currentFret,
  onSelect,
  onClose,
}: NoteCorrectionPanelProps) {
  const [pitch, setPitch] = useState(originalPitch)
  const [duration, setDuration] = useState(originalDuration)
  const [fret, setFret] = useState(currentFret ?? 0)
  const [string, setString] = useState(currentString ?? 1)

  const noteName = midiToNoteName(pitch)
  const octave = Math.floor(pitch / 12 - 1)

  const handleConfirm = () => {
    const corrected: { pitch?: number; duration?: number; start_time?: number; string?: number; fret?: number } = {}
    if (pitch !== originalPitch) corrected.pitch = pitch
    if (duration !== originalDuration) corrected.duration = duration
    if (Object.keys(corrected).length === 0 && fret === (currentFret ?? 0) && string === (currentString ?? 1)) {
      onClose()
      return
    }
    corrected.string = string
    corrected.fret = fret
    onSelect(noteIndex, corrected)
    onClose()
  }

  const hasChanges = pitch !== originalPitch || duration !== originalDuration || fret !== (currentFret ?? 0) || string !== (currentString ?? 1)

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
            <View className="flex-row justify-end gap-2">
              <AnimatedPressable
                onPress={onClose}
                className="rounded-full border border-wood-600/40 bg-wood-900/10 px-4 py-2"
              >
                <Text className="font-sans-medium text-sm text-muted-brown">Cancel</Text>
              </AnimatedPressable>
              <AnimatedPressable
                onPress={handleConfirm}
                disabled={!hasChanges}
                className={`rounded-full border px-4 py-2 ${
                  !hasChanges
                    ? 'border-wood-600/40 bg-wood-900/10 opacity-50'
                    : 'border-amber-accent bg-amber-accent'
                }`}
              >
                <Text className={`font-sans-medium text-sm ${!hasChanges ? 'text-muted-brown' : 'text-wood-900'}`}>
                  Confirm
                </Text>
              </AnimatedPressable>
            </View>
          </View>
        </View>
      </View>
    </Modal>
  )
}

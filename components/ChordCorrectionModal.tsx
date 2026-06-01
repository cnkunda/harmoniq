import { useState } from 'react'
import { Modal, ScrollView, View, Text } from 'react-native'

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
import { getDiatonicChords, getChromaticChords, type DiatonicChord } from '@/src/music/diatonicChords'

type ChordCorrectionModalProps = {
  visible: boolean
  currentChord: string
  songKey: string | null
  eventIndex: number
  onSelect: (eventIndex: number, newChord: string) => void
  onClose: () => void
}

export function ChordCorrectionModal({
  visible,
  currentChord,
  songKey,
  eventIndex,
  onSelect,
  onClose,
}: ChordCorrectionModalProps) {
  const [selected, setSelected] = useState(currentChord)
  const [showChromatic, setShowChromatic] = useState(false)

  const diatonic = songKey ? getDiatonicChords(songKey) : []
  const chromatic = getChromaticChords()

  const handleConfirm = () => {
    if (selected !== currentChord) {
      onSelect(eventIndex, selected)
    }
    onClose()
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View className="flex-1">
        <AnimatedPressable
          className="absolute inset-0 bg-wood-900/50"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close chord correction"
        />
        <View className="absolute inset-0 bg-wood-900/35" pointerEvents="none" />

        <View className="flex-1 justify-end px-4 pb-8 pt-12">
          <AnimatedPressable className="absolute inset-0" onPress={onClose} />
          <View className="rounded-3xl border border-wood-600/70 bg-wood-900 p-4">
            {/* Header */}
            <View className="mb-4 flex-row items-center justify-between">
              <Text className="font-serif text-lg text-cream">Correct Chord</Text>
              <Text className="font-mono text-sm text-muted-brown">
                {formatChordDisplay(currentChord)}
              </Text>
            </View>

            {/* Current + Selected preview */}
            <View className="mb-4 flex-row items-center justify-center gap-4">
              <View className="items-center">
                <Text className={SECTION_EYEBROW_CLASS}>Current</Text>
                <ChordDiagram name={currentChord} size="md" />
              </View>
              <Text className="text-lg text-muted-brown">→</Text>
              <View className="items-center">
                <Text className={SECTION_EYEBROW_CLASS}>New</Text>
                <ChordDiagram name={selected} size="md" isActive />
              </View>
            </View>

            {/* Diatonic chords */}
            {diatonic.length > 0 && (
              <View className="mb-3">
                <Text className={SECTION_EYEBROW_CLASS}>Diatonic in {songKey}</Text>
                <View className="mt-2 flex-row flex-wrap gap-1.5">
                  {diatonic.map((d) => (
                    <DiatonicChip
                      key={d.symbol}
                      chord={d}
                      isSelected={selected === d.symbol}
                      onSelect={setSelected}
                    />
                  ))}
                </View>
              </View>
            )}

            {/* Chromatic toggle */}
            <AnimatedPressable
              onPress={() => setShowChromatic(!showChromatic)}
              className="mb-2 self-start"
            >
              <Text className="font-sans text-xs text-amber-accent">
                {showChromatic ? 'Hide chromatic' : 'Show all chords…'}
              </Text>
            </AnimatedPressable>

            {/* Chromatic grid */}
            {showChromatic && (
              <ScrollView style={{ maxHeight: 200 }} className="mb-3">
                <View className="flex-row flex-wrap gap-1">
                  {chromatic.map((c) => (
                    <AnimatedPressable
                      key={c.symbol}
                      onPress={() => setSelected(c.symbol)}
                      className={`${CHOICE_CHIP_BASE} ${selected === c.symbol ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} px-2 py-1`}
                    >
                      <Text
                        className={`font-mono text-[10px] ${selected === c.symbol ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF}`}
                      >
                        {c.display}
                      </Text>
                    </AnimatedPressable>
                  ))}
                </View>
              </ScrollView>
            )}

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
                disabled={selected === currentChord}
                className={`rounded-full border px-4 py-2 ${
                  selected === currentChord
                    ? 'border-wood-600/40 bg-wood-900/10 opacity-50'
                    : 'border-amber-accent bg-amber-accent'
                }`}
              >
                <Text
                  className={`font-sans-medium text-sm ${
                    selected === currentChord ? 'text-muted-brown' : 'text-wood-900'
                  }`}
                >
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

// ---- Internal chip component ----

function DiatonicChip({
  chord,
  isSelected,
  onSelect,
}: {
  chord: DiatonicChord
  isSelected: boolean
  onSelect: (symbol: string) => void
}) {
  return (
    <AnimatedPressable
      onPress={() => onSelect(chord.symbol)}
      className={`${CHOICE_CHIP_BASE} ${isSelected ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF}`}
    >
      <View className="items-center">
        <Text className={`font-mono text-[11px] ${isSelected ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF}`}>
          {chord.display}
        </Text>
        <Text className={`text-[9px] ${isSelected ? 'text-wood-900/70' : 'text-muted-brown/60'}`}>
          {chord.roman}
        </Text>
      </View>
    </AnimatedPressable>
  )
}

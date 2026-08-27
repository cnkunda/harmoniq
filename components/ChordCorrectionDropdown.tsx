import React, { useCallback, useState } from 'react'
import { View, Text, TextInput, FlatList } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

export interface ChordCorrectionDropdownProps {
  currentChord: string
  beatIndex: number
  keySignature?: string
  onSelect: (beatIndex: number, chord: string) => void
  onCancel: () => void
  style?: object
  className?: string
}

const CHORD_QUALITIES = ['maj', 'min', '7', 'maj7', 'min7', '9', 'min9', 'sus4', 'dim', 'aug', '6', 'min6']
const ROOT_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function generateChordSuggestions(keySignature?: string): string[] {
  const chords: string[] = ['N']
  for (const root of ROOT_NOTES) {
    for (const quality of CHORD_QUALITIES) {
      chords.push(`${root}:${quality}`)
    }
  }
  return chords
}

export function ChordCorrectionDropdown({
  currentChord,
  beatIndex,
  keySignature,
  onSelect,
  onCancel,
  style,
}: ChordCorrectionDropdownProps) {
  const [query, setQuery] = useState(currentChord)
  const allChords = generateChordSuggestions(keySignature)

  const filtered = query.trim()
    ? allChords.filter((c) => c.toLowerCase().includes(query.toLowerCase()))
    : allChords.slice(0, 30)

  const handleSelect = useCallback(
    (chord: string) => {
      onSelect(beatIndex, chord)
    },
    [beatIndex, onSelect],
  )

  return (
    <View
      style={[
        {
          backgroundColor: colors.wood[800],
          borderWidth: 1,
          borderColor: colors.wood[600],
          borderRadius: 12,
          padding: 12,
          maxHeight: 300,
        },
        style,
      ]}
    >
      <View className="flex-row items-center justify-between mb-2">
        <Text className="text-sm font-serif" style={{ color: colors.cream }}>
          Correct Chord (beat {beatIndex})
        </Text>
        <AnimatedPressable onPress={onCancel} haptic="light" className="rounded-md px-2 py-1">
          <Text className="text-xs font-sans" style={{ color: colors.muted.light }}>
            Cancel
          </Text>
        </AnimatedPressable>
      </View>

      <TextInput
        value={query}
        onChangeText={setQuery}
        placeholder="Search chords..."
        placeholderTextColor={colors.muted.light}
        className="rounded-lg px-3 py-2 mb-2 font-mono text-sm"
        style={{
          color: colors.cream,
          backgroundColor: colors.wood[700],
          borderWidth: 1,
          borderColor: colors.wood[600],
        }}
        autoCapitalize="none"
        autoCorrect={false}
      />

      <FlatList
        data={filtered}
        keyExtractor={(item) => item}
        renderItem={({ item }) => (
          <AnimatedPressable
            onPress={() => handleSelect(item)}
            haptic="light"
            className="rounded-md px-3 py-2 mb-1"
            style={{
              backgroundColor: item === currentChord ? colors.wood[600] : colors.wood[700],
            }}
          >
            <Text
              className="text-sm font-mono"
              style={{ color: item === currentChord ? colors.amber.accent : colors.cream }}
            >
              {item}
            </Text>
          </AnimatedPressable>
        )}
        style={{ maxHeight: 180 }}
        showsVerticalScrollIndicator={false}
      />
    </View>
  )
}

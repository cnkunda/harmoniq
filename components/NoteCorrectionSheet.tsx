import React, { useCallback, useState } from 'react'
import { View, Text, TextInput } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'

export interface NoteCorrectionSheetProps {
  noteIndex: number
  originalNote: {
    pitch: number
    start_time: number
    duration: number
    velocity: number
  }
  onSave: (noteIndex: number, corrections: {
    pitch?: number
    start_time?: number
    duration?: number
    velocity?: number
    string?: number
    fret?: number
  }) => void
  onCancel: () => void
  style?: object
  className?: string
}

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function midiToNoteName(midi: number): string {
  const name = NOTE_NAMES[midi % 12]
  const octave = Math.floor(midi / 12) - 1
  return `${name}${octave}`
}

export function NoteCorrectionSheet({
  noteIndex,
  originalNote,
  onSave,
  onCancel,
  style,
}: NoteCorrectionSheetProps) {
  const [pitch, setPitch] = useState(String(originalNote.pitch))
  const [duration, setDuration] = useState(originalNote.duration.toFixed(3))
  const [velocity, setVelocity] = useState(String(originalNote.velocity))
  const [guitarString, setGuitarString] = useState('')
  const [fret, setFret] = useState('')

  const handleSave = useCallback(() => {
    const corrections: {
      pitch?: number
      start_time?: number
      duration?: number
      velocity?: number
      string?: number
      fret?: number
    } = {}

    const pitchVal = parseInt(pitch, 10)
    if (!isNaN(pitchVal) && pitchVal !== originalNote.pitch) {
      corrections.pitch = pitchVal
    }
    const durVal = parseFloat(duration)
    if (!isNaN(durVal) && Math.abs(durVal - originalNote.duration) > 0.001) {
      corrections.duration = durVal
    }
    const velVal = parseInt(velocity, 10)
    if (!isNaN(velVal) && velVal !== originalNote.velocity) {
      corrections.velocity = velVal
    }
    const strVal = parseInt(guitarString, 10)
    if (!isNaN(strVal) && strVal >= 1 && strVal <= 6) {
      corrections.string = strVal
    }
    const fretVal = parseInt(fret, 10)
    if (!isNaN(fretVal) && fretVal >= 0) {
      corrections.fret = fretVal
    }

    if (Object.keys(corrections).length > 0) {
      onSave(noteIndex, corrections)
    }
  }, [pitch, duration, velocity, guitarString, fret, noteIndex, originalNote, onSave])

  return (
    <View
      style={[
        {
          backgroundColor: colors.wood[800],
          borderWidth: 1,
          borderColor: colors.wood[600],
          borderRadius: 12,
          padding: 12,
        },
        style,
      ]}
    >
      <View className="flex-row items-center justify-between mb-3">
        <Text className="text-sm font-serif" style={{ color: colors.cream }}>
          Note {noteIndex} ({midiToNoteName(originalNote.pitch)})
        </Text>
        <View className="flex-row gap-2">
          <AnimatedPressable onPress={onCancel} haptic="light" className="rounded-md px-2 py-1">
            <Text className="text-xs font-sans" style={{ color: colors.muted.brown }}>
              Cancel
            </Text>
          </AnimatedPressable>
          <AnimatedPressable onPress={handleSave} haptic="medium" className="rounded-md px-3 py-1" style={{ backgroundColor: colors.amber.accent }}>
            <Text className="text-xs font-sans-medium" style={{ color: colors.wood[900] }}>
              Save
            </Text>
          </AnimatedPressable>
        </View>
      </View>

      <View className="gap-2">
        {/* Pitch */}
        <View className="flex-row items-center gap-2">
          <Text className="text-xs font-sans w-16" style={{ color: colors.muted.brown }}>
            Pitch
          </Text>
          <TextInput
            value={pitch}
            onChangeText={setPitch}
            keyboardType="numeric"
            className="rounded-md px-2 py-1 font-mono text-sm flex-1"
            style={{
              color: colors.cream,
              backgroundColor: colors.wood[700],
            }}
          />
          <Text className="text-xs font-sans" style={{ color: colors.muted.brown }}>
            {midiToNoteName(parseInt(pitch, 10) || originalNote.pitch)}
          </Text>
        </View>

        {/* Duration */}
        <View className="flex-row items-center gap-2">
          <Text className="text-xs font-sans w-16" style={{ color: colors.muted.brown }}>
            Duration
          </Text>
          <TextInput
            value={duration}
            onChangeText={setDuration}
            keyboardType="numeric"
            className="rounded-md px-2 py-1 font-mono text-sm flex-1"
            style={{
              color: colors.cream,
              backgroundColor: colors.wood[700],
            }}
          />
          <Text className="text-xs font-sans" style={{ color: colors.muted.brown }}>sec</Text>
        </View>

        {/* Velocity */}
        <View className="flex-row items-center gap-2">
          <Text className="text-xs font-sans w-16" style={{ color: colors.muted.brown }}>
            Velocity
          </Text>
          <TextInput
            value={velocity}
            onChangeText={setVelocity}
            keyboardType="numeric"
            className="rounded-md px-2 py-1 font-mono text-sm flex-1"
            style={{
              color: colors.cream,
              backgroundColor: colors.wood[700],
            }}
          />
        </View>

        {/* Guitar string + fret */}
        <View className="flex-row items-center gap-2">
          <Text className="text-xs font-sans w-16" style={{ color: colors.muted.brown }}>
            String
          </Text>
          <TextInput
            value={guitarString}
            onChangeText={setGuitarString}
            keyboardType="numeric"
            placeholder="1-6"
            placeholderTextColor={colors.muted.brown}
            className="rounded-md px-2 py-1 font-mono text-sm flex-1"
            style={{
              color: colors.cream,
              backgroundColor: colors.wood[700],
            }}
          />
          <Text className="text-xs font-sans w-16" style={{ color: colors.muted.brown }}>
            Fret
          </Text>
          <TextInput
            value={fret}
            onChangeText={setFret}
            keyboardType="numeric"
            placeholder="0+"
            placeholderTextColor={colors.muted.brown}
            className="rounded-md px-2 py-1 font-mono text-sm flex-1"
            style={{
              color: colors.cream,
              backgroundColor: colors.wood[700],
            }}
          />
        </View>
      </View>
    </View>
  )
}

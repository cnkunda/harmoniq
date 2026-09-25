import { Heart, Play, SkipBack } from 'lucide-react-native'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { toast } from '@/components/ToastConfig'
import { FretboardDiagram } from '@/components/FretboardDiagram'
import colors from '@/src/constants/colors'
import {
  CHOICE_CHIP_BASE,
  CHOICE_CHIP_OFF,
  CHOICE_CHIP_ON,
  CHOICE_LABEL_SANS_OFF,
  CHOICE_LABEL_SANS_ON,
  SECTION_EYEBROW_CLASS,
} from '@/src/constants/uiTokens'
import {
  getCagedPatternForScale,
  type CagedForm,
} from '@/src/music/cagedPatterns'
import { CHROMATIC_NOTE_NAMES } from '@/src/music/noteNames'
import { playNote, playScale, stopPlayback } from '@/src/music/scaleAudition'
import {
  addFavorite,
  getFavorites,
  isFavorite,
  removeFavorite,
  type ScaleFavorite,
} from '@/src/music/scaleFavorites'
import {
  SCALE_DB,
  getScale,
  getScalePitchClasses,
  getScalesByFamily,
  type ScaleFamily,
} from '@/src/music/scales'

const SCALE_DEGREE_LABELS: Record<number, string> = {
  0: '1', 1: 'b2', 2: '2', 3: 'b3', 4: '3', 5: '4',
  6: 'b5', 7: '5', 8: '#5', 9: '6', 10: 'b7', 11: '7',
}

const FAMILIES: ScaleFamily[] = [
  'diatonic',
  'harmonic_minor',
  'melodic_minor',
  'pentatonic',
  'blues',
  'symmetrical',
  'other',
]

const FAMILY_LABELS: Record<ScaleFamily, string> = {
  diatonic: 'Diatonic',
  harmonic_minor: 'Harmonic Min',
  melodic_minor: 'Melodic Min',
  pentatonic: 'Pentatonic',
  blues: 'Blues',
  symmetrical: 'Symmetrical',
  other: 'Other',
}

const CAGED_FORMS: CagedForm[] = ['E', 'A', 'D', 'C', 'G']

const DEFAULT_ROOT = 0
const DEFAULT_SCALE_KEY = 'ionian'
const DEFAULT_FAMILY: ScaleFamily = 'diatonic'
const DEFAULT_BPM = 80

export default function ScaleExplorerScreen() {
  const [selectedRoot, setSelectedRoot] = useState(DEFAULT_ROOT)
  const [selectedScaleKey, setSelectedScaleKey] = useState(DEFAULT_SCALE_KEY)
  const [selectedFamily, setSelectedFamily] = useState<ScaleFamily>(DEFAULT_FAMILY)
  const [selectedCagedForm, setSelectedCagedForm] = useState<CagedForm | null>(null)
  const [overlayMode, setOverlayMode] = useState<'off' | 'note_names' | 'scale_degrees'>('off')
  const [selectedNote, setSelectedNote] = useState<{
    string: number
    fret: number
    midi: number
  } | null>(null)
  const [bpm, setBpm] = useState(DEFAULT_BPM)
  const [favorites, setFavorites] = useState<ScaleFavorite[]>([])
  const [isPlaying, setIsPlaying] = useState(false)

  const scaleEntry = useMemo(() => getScale(selectedScaleKey), [selectedScaleKey])

  const scalePCs = useMemo(
    () => getScalePitchClasses(selectedRoot, selectedScaleKey) ?? [],
    [selectedRoot, selectedScaleKey],
  )

  const scalesInFamily = useMemo(
    () => getScalesByFamily(selectedFamily),
    [selectedFamily],
  )

  const cagedCells = useMemo(() => {
    if (!selectedCagedForm || !scaleEntry) return null
    return getCagedPatternForScale(selectedCagedForm, selectedRoot, scaleEntry.intervals)
  }, [selectedCagedForm, selectedRoot, scaleEntry])

  const noteNames = useMemo(
    () => scalePCs.map((pc) => CHROMATIC_NOTE_NAMES[pc]),
    [scalePCs],
  )

  const degreeLabels = useMemo(
    () => (scaleEntry?.intervals ?? []).map((iv) => SCALE_DEGREE_LABELS[iv % 12] ?? '?'),
    [scaleEntry],
  )

  const rootName = CHROMATIC_NOTE_NAMES[selectedRoot]

  const isCurrentFav = useMemo(
    () => favorites.some((f) => f.scaleKey === selectedScaleKey && f.rootPitchClass === selectedRoot),
    [favorites, selectedScaleKey, selectedRoot],
  )

  useEffect(() => {
    void getFavorites().then(setFavorites)
  }, [])

  const handleSelectScale = useCallback((key: string) => {
    setSelectedScaleKey(key)
    setSelectedNote(null)
    setSelectedCagedForm(null)
  }, [])

  const handleSelectRoot = useCallback((pc: number) => {
    setSelectedRoot(pc)
    setSelectedNote(null)
  }, [])

  const handleSelectFamily = useCallback((family: ScaleFamily) => {
    setSelectedFamily(family)
    setSelectedScaleKey(DEFAULT_SCALE_KEY)
    setSelectedNote(null)
    setSelectedCagedForm(null)

    const scales = getScalesByFamily(family)
    if (scales.length > 0) {
      const match = Object.entries(SCALE_DB).find(([, e]) => e.name === scales[0].name)
      if (match) setSelectedScaleKey(match[0])
    }
  }, [])

  const handleSelectNote = useCallback(
    (note: { string: number; fret: number; midi: number }) => {
      setSelectedNote(note)
      void playNote(note.midi)
    },
    [],
  )

  const handlePlayScale = useCallback(async () => {
    if (!scaleEntry || isPlaying) return
    setIsPlaying(true)
    const rootMidi = 60 + selectedRoot
    try {
      await playScale(rootMidi, scaleEntry.intervals, bpm, (midi) => {
        setSelectedNote({ string: 0, fret: 0, midi })
      })
    } catch {
      toast.error('Playback stopped')
    } finally {
      setIsPlaying(false)
      setSelectedNote(null)
    }
  }, [scaleEntry, isPlaying, selectedRoot, bpm])

  const handleStopPlayback = useCallback(() => {
    stopPlayback()
    setIsPlaying(false)
    setSelectedNote(null)
  }, [])

  const handleToggleFavorite = useCallback(async () => {
    if (isCurrentFav) {
      await removeFavorite(selectedScaleKey, selectedRoot)
      setFavorites((prev) =>
        prev.filter((f) => !(f.scaleKey === selectedScaleKey && f.rootPitchClass === selectedRoot)),
      )
      toast.success('Removed from favorites')
    } else {
      const fav: ScaleFavorite = {
        scaleKey: selectedScaleKey,
        rootPitchClass: selectedRoot,
      }
      await addFavorite(fav)
      setFavorites((prev) => [...prev, fav])
      toast.success('Added to favorites')
    }
  }, [isCurrentFav, selectedScaleKey, selectedRoot])

  const bpmDecrease = useCallback(() => {
    setBpm((p) => Math.max(30, p - 5))
  }, [])

  const bpmIncrease = useCallback(() => {
    setBpm((p) => Math.min(180, p + 5))
  }, [])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingBottom: 40 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View className="w-full max-w-4xl self-center px-4 pb-8 pt-4">
          {/* ---- Header ---- */}
          <View className="mb-6">
            <Text className="font-serif text-2xl text-cream">Scale Explorer</Text>
            <Text className="mt-1 font-sans text-sm text-muted-brown">
              Browse, visualize, and play 30+ scales across all keys
            </Text>
          </View>

          {/* ---- Root Picker ---- */}
          <View className="mb-4">
            <Text className={SECTION_EYEBROW_CLASS}>Root</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              className="mt-2"
            >
              <View className="flex-row gap-1.5">
                {CHROMATIC_NOTE_NAMES.map((name, pc) => (
                  <AnimatedPressable
                    key={name}
                    onPress={() => handleSelectRoot(pc)}
                    className={`${CHOICE_CHIP_BASE} ${
                      selectedRoot === pc ? 'border-amber-accent bg-amber-accent' : CHOICE_CHIP_OFF
                    }`}
                    accessibilityRole="button"
                    accessibilityLabel={`Root ${name}`}
                    accessibilityState={{ selected: selectedRoot === pc }}
                  >
                    <Text
                      className={
                        selectedRoot === pc ? 'font-sans-medium text-xs text-wood-900' : 'font-sans text-xs text-muted-brown'
                      }
                    >
                      {name}
                    </Text>
                  </AnimatedPressable>
                ))}
              </View>
            </ScrollView>
          </View>

          {/* ---- Family Tabs ---- */}
          <View className="mb-4">
            <Text className={SECTION_EYEBROW_CLASS}>Family</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              className="mt-2"
            >
              <View className="flex-row gap-1.5">
                {FAMILIES.map((family) => (
                  <AnimatedPressable
                    key={family}
                    onPress={() => handleSelectFamily(family)}
                    className={`${CHOICE_CHIP_BASE} ${
                      selectedFamily === family ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF
                    }`}
                    accessibilityRole="button"
                    accessibilityLabel={FAMILY_LABELS[family]}
                    accessibilityState={{ selected: selectedFamily === family }}
                  >
                    <Text
                      className={
                        selectedFamily === family ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF
                      }
                    >
                      {FAMILY_LABELS[family]}
                    </Text>
                  </AnimatedPressable>
                ))}
              </View>
            </ScrollView>
          </View>

          {/* ---- Scale Grid ---- */}
          <View className="mb-4">
            <Text className={SECTION_EYEBROW_CLASS}>Scales</Text>
            <View className="mt-2 gap-1">
              {scalesInFamily.map((entry) => {
                const dbKey =
                  Object.entries(SCALE_DB).find(([, e]) => e.name === entry.name)?.[0] ?? ''
                const isSelected = selectedScaleKey === dbKey
                const isFav = favorites.some(
                  (f) => f.scaleKey === dbKey && f.rootPitchClass === selectedRoot,
                )
                return (
                  <AnimatedPressable
                    key={dbKey}
                    onPress={() => handleSelectScale(dbKey)}
                    className={`flex-row items-center rounded-lg border px-3 py-2.5 ${
                      isSelected
                        ? 'border-amber-accent/60 bg-amber-accent/10'
                        : 'border-wood-700/50 bg-wood-800/40'
                    }`}
                    accessibilityRole="button"
                    accessibilityLabel={`Scale ${entry.name}`}
                    accessibilityState={{ selected: isSelected }}
                  >
                    <View className="flex-1">
                      <Text
                        className={`font-sans-medium text-sm ${
                          isSelected ? 'text-cream' : 'text-cream/80'
                        }`}
                      >
                        {entry.name}
                      </Text>
                      {entry.aliases.length > 0 && (
                        <Text className="mt-0.5 font-sans text-[11px] text-muted-brown">
                          {entry.aliases.join(', ')}
                        </Text>
                      )}
                    </View>
                    <AnimatedPressable
                      onPress={() => {
                        if (isFav) {
                          void removeFavorite(dbKey, selectedRoot).then(() => {
                            setFavorites((prev) =>
                              prev.filter(
                                (f) => !(f.scaleKey === dbKey && f.rootPitchClass === selectedRoot),
                              ),
                            )
                          })
                        } else {
                          void addFavorite({ scaleKey: dbKey, rootPitchClass: selectedRoot }).then(
                            () => {
                              setFavorites((prev) => [
                                ...prev,
                                { scaleKey: dbKey, rootPitchClass: selectedRoot },
                              ])
                            },
                          )
                        }
                      }}
                      haptic="light"
                      className="ml-2 h-8 w-8 items-center justify-center rounded-full"
                      accessibilityRole="button"
                      accessibilityLabel={isFav ? 'Remove from favorites' : 'Add to favorites'}
                    >
                      <Heart
                        size={16}
                        color={isFav ? colors.danger : colors.muted.brown}
                        fill={isFav ? colors.danger : 'transparent'}
                        strokeWidth={1.5}
                      />
                    </AnimatedPressable>
                  </AnimatedPressable>
                )
              })}
            </View>
          </View>

          {/* ---- CAGED Position Picker ---- */}
          <View className="mb-4">
            <Text className={SECTION_EYEBROW_CLASS}>CAGED Position</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              className="mt-2"
            >
              <View className="flex-row gap-1.5">
                <AnimatedPressable
                  onPress={() => setSelectedCagedForm(null)}
                  className={`${CHOICE_CHIP_BASE} ${
                    selectedCagedForm == null ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF
                  }`}
                  accessibilityRole="button"
                  accessibilityLabel="No CAGED position"
                  accessibilityState={{ selected: selectedCagedForm == null }}
                >
                  <Text
                    className={
                      selectedCagedForm == null ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF
                    }
                  >
                    Off
                  </Text>
                </AnimatedPressable>
                {CAGED_FORMS.map((form) => (
                  <AnimatedPressable
                    key={form}
                    onPress={() => {
                      setSelectedCagedForm(selectedCagedForm === form ? null : form)
                    }}
                    className={`${CHOICE_CHIP_BASE} ${
                      selectedCagedForm === form ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF
                    }`}
                    accessibilityRole="button"
                    accessibilityLabel={`CAGED form ${form}`}
                    accessibilityState={{ selected: selectedCagedForm === form }}
                  >
                    <Text
                      className={
                        selectedCagedForm === form ? CHOICE_LABEL_SANS_ON : CHOICE_LABEL_SANS_OFF
                      }
                    >
                      {form}
                    </Text>
                  </AnimatedPressable>
                ))}
              </View>
            </ScrollView>
          </View>

          {/* ---- Fretboard ---- */}
          <FretboardDiagram
            keyLabel={`${rootName} ${scaleEntry?.name ?? ''}`}
            positionLabel={`${FAMILY_LABELS[selectedFamily]}`}
            capoText=""
            scalePitchClasses={scalePCs.length > 0 ? scalePCs : null}
            degreeRootPitchClass={selectedRoot}
            selectedNote={selectedNote}
            onSelectNote={handleSelectNote}
            overlayMode={overlayMode}
            onOverlayModeChange={setOverlayMode}
            showOverlayControls
            enableKeyboardInput
            fretGuideCells={cagedCells}
            activeGuideIndex={null}
            harmonicContextMode="key_context"
          />

          {/* ---- Play Controls ---- */}
          <View className="mb-4 mt-4">
            <Text className={SECTION_EYEBROW_CLASS}>Play Scale</Text>
            <View className="mt-2 flex-row items-center gap-3">
              <AnimatedPressable
                onPress={isPlaying ? handleStopPlayback : handlePlayScale}
                haptic="medium"
                className={`flex-row items-center gap-2 rounded-xl px-5 py-3 ${
                  isPlaying
                    ? 'bg-danger/80'
                    : 'bg-amber-accent'
                }`}
                accessibilityRole="button"
                accessibilityLabel={isPlaying ? 'Stop playback' : 'Play scale'}
              >
                {isPlaying ? (
                  <SkipBack size={18} color={colors.cream} strokeWidth={2} />
                ) : (
                  <Play size={18} color={colors.wood[900]} fill={colors.wood[900]} strokeWidth={0} />
                )}
                <Text
                  className={`font-sans-medium text-sm ${
                    isPlaying ? 'text-cream' : 'text-wood-900'
                  }`}
                >
                  {isPlaying ? 'Stop' : 'Play scale'}
                </Text>
              </AnimatedPressable>

              <View className="flex-row items-center gap-2">
                <AnimatedPressable
                  onPress={bpmDecrease}
                  className="h-8 w-8 items-center justify-center rounded-full border border-wood-600/40"
                  accessibilityRole="button"
                  accessibilityLabel="Decrease BPM"
                >
                  <Text className="font-sans text-sm text-cream">−</Text>
                </AnimatedPressable>
                <View className="min-w-[48px] items-center">
                  <Text className="font-serif text-lg text-amber-accent">{bpm}</Text>
                  <Text className="font-sans text-[10px] text-muted-brown">BPM</Text>
                </View>
                <AnimatedPressable
                  onPress={bpmIncrease}
                  className="h-8 w-8 items-center justify-center rounded-full border border-wood-600/40"
                  accessibilityRole="button"
                  accessibilityLabel="Increase BPM"
                >
                  <Text className="font-sans text-sm text-cream">+</Text>
                </AnimatedPressable>
              </View>
            </View>
          </View>

          {/* ---- Info Card ---- */}
          {scaleEntry && (
            <View className="rounded-xl border border-wood-700/50 bg-wood-800/40 p-4">
              <View className="mb-3 flex-row items-center justify-between">
                <Text className="font-serif text-lg text-cream">
                  {rootName} {scaleEntry.name}
                </Text>
                <AnimatedPressable
                  onPress={handleToggleFavorite}
                  haptic="light"
                  className="h-9 w-9 items-center justify-center rounded-full"
                  accessibilityRole="button"
                  accessibilityLabel={isCurrentFav ? 'Remove from favorites' : 'Add to favorites'}
                >
                  <Heart
                    size={18}
                    color={isCurrentFav ? colors.danger : colors.muted.brown}
                    fill={isCurrentFav ? colors.danger : 'transparent'}
                    strokeWidth={1.5}
                  />
                </AnimatedPressable>
              </View>

              <View className="gap-2">
                <View className="flex-row">
                  <Text className="w-20 font-sans text-xs text-muted-brown">Notes</Text>
                  <Text className="flex-1 font-sans text-sm text-cream">
                    {noteNames.join(' · ')}
                  </Text>
                </View>
                <View className="flex-row">
                  <Text className="w-20 font-sans text-xs text-muted-brown">Intervals</Text>
                  <Text className="flex-1 font-sans text-sm text-cream">
                    {degreeLabels.join(' · ')}
                  </Text>
                </View>
                <View className="flex-row">
                  <Text className="w-20 font-sans text-xs text-muted-brown">Family</Text>
                  <Text className="flex-1 font-sans text-sm text-cream">
                    {FAMILY_LABELS[scaleEntry.family]}
                  </Text>
                </View>
                {scaleEntry.aliases.length > 0 && (
                  <View className="flex-row">
                    <Text className="w-20 font-sans text-xs text-muted-brown">Aliases</Text>
                    <Text className="flex-1 font-sans text-sm text-cream">
                      {scaleEntry.aliases.join(' · ')}
                    </Text>
                  </View>
                )}
              </View>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}

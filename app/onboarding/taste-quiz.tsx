import { useLocalSearchParams, useRouter } from 'expo-router'
import { Guitar, Music2, Search } from 'lucide-react-native'
import { useCallback, useMemo, useState } from 'react'
import { ScrollView, Text, TextInput, useWindowDimensions, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { OnboardingScreenShell } from '@/components/onboarding/OnboardingScreenShell'
import { toast } from '@/components/ToastConfig'
import { deriveTasteProfile } from '@/src/api/analyze'
import colors from '@/src/constants/colors'
import { commitTasteQuizProfile } from '@/src/db/client'
import {
  TASTE_QUIZ_ARTISTS,
  TASTE_QUIZ_VIBE_CARDS,
  type TasteQuizVibeId,
} from '@/src/taste/tasteQuizSeeds'
import { useSkillStore } from '@/src/stores/skillStore'

type Experience = 'beginner' | 'intermediate' | 'advanced'

const EXPERIENCE_OPTIONS: ReadonlyArray<{ id: Experience; title: string; blurb: string }> = [
  {
    id: 'beginner',
    title: 'Beginner',
    blurb: 'Mapping the fretboard and timing; chords or basics may be stronger than single-note lines.',
  },
  {
    id: 'intermediate',
    title: 'Intermediate',
    blurb: 'Comfortable with chords and rhythm; building lead vocabulary—scales, boxes, and first phrases.',
  },
  {
    id: 'advanced',
    title: 'Advanced',
    blurb: 'Solid repertoire and lead fluency; refining expression, speed where it serves the phrase.',
  },
]

/** Matches OnboardingScreenShell `max-w-md` (28rem) inner content after `px-6`. */
const SHELL_MAX_CONTENT_PX = 448
const SHELL_HORIZONTAL_PADDING_PX = 48
const ARTIST_GRID_GAP_PX = 12

export default function TasteQuizScreen() {
  const router = useRouter()
  const { width: windowWidth } = useWindowDimensions()
  const rawUpdate = useLocalSearchParams<{ update?: string | string[] }>().update
  const updateParam = Array.isArray(rawUpdate) ? rawUpdate[0] : rawUpdate
  const isUpdateFlow = updateParam === '1'
  const loadSkills = useSkillStore((s) => s.loadFromDb)

  const artistTileWidth = useMemo(() => {
    const contentW = Math.min(SHELL_MAX_CONTENT_PX, windowWidth) - SHELL_HORIZONTAL_PADDING_PX
    return Math.max(1, Math.floor((contentW - ARTIST_GRID_GAP_PX) / 2))
  }, [windowWidth])

  const [step, setStep] = useState(0)
  const [query, setQuery] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [vibe, setVibe] = useState<TasteQuizVibeId | null>(null)
  const [experience, setExperience] = useState<Experience | null>(null)
  const [busy, setBusy] = useState(false)

  const filteredArtists = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return [...TASTE_QUIZ_ARTISTS]
    return TASTE_QUIZ_ARTISTS.filter(
      (a) => a.name.toLowerCase().includes(q) || a.styleTag.toLowerCase().includes(q),
    )
  }, [query])

  const toggleArtist = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else {
        if (next.size >= 8) {
          toast.error('Pick up to eight artists for this pass.')
          return prev
        }
        next.add(id)
      }
      return next
    })
  }, [])

  const canNextStep0 = selectedIds.size >= 1
  const canNextStep1 = vibe != null
  const canSubmit = experience != null && vibe != null && selectedIds.size >= 1

  const submit = () => {
    if (!canSubmit || busy || !vibe || !experience) return
    void (async () => {
      setBusy(true)
      try {
        const names = TASTE_QUIZ_ARTISTS.filter((a) => selectedIds.has(a.id)).map((a) => a.name)
        const taste = await deriveTasteProfile({
          quiz_answers: {
            selected_artists: names,
            selected_style: vibe,
            experience_level: experience,
          },
        })
        await commitTasteQuizProfile(taste, experience)
        await loadSkills()
        toast.success('Preferences saved.')
        if (isUpdateFlow) {
          router.back()
        } else {
          router.replace('/onboarding/mic')
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not save preferences. Try again.')
      } finally {
        setBusy(false)
      }
    })()
  }

  const goNext = () => {
    if (step === 0 && !canNextStep0) {
      toast.error('Pick at least one artist to continue.')
      return
    }
    if (step === 1 && !canNextStep1) {
      toast.error('Pick a vibe to continue.')
      return
    }
    if (step < 2) setStep((s) => s + 1)
  }

  const goBack = () => {
    if (step > 0) setStep((s) => s - 1)
    else if (isUpdateFlow) router.back()
    else router.replace('/onboarding')
  }

  return (
    <OnboardingScreenShell
      currentStep={step + 1}
      totalSteps={3}
      showBack
      onBack={goBack}
      scrollable
    >
      {step === 0 ? (
        <View className="w-full py-2">
          <Text className="text-center font-serif text-2xl text-cream">Artists you love</Text>
          <Text className="mt-2 text-center font-sans text-sm text-muted-brown">
            Pick at least one name (up to eight). Search filters the grid — static list, not Spotify search.
          </Text>
          <View className="mt-4 flex-row items-center rounded-lg border border-wood-600/50 bg-wood-900/50 px-3 py-2.5">
            <Search color={colors.muted.brown} size={18} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search artists…"
              placeholderTextColor={colors.muted.brown}
              className="ml-2 flex-1 font-sans text-sm text-cream"
              accessibilityLabel="Filter artist list"
            />
          </View>
          <ScrollView
            className="mt-4 max-h-[340px] w-full"
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ paddingBottom: 8 }}
          >
            <View
              className="w-full flex-row flex-wrap"
              style={{ gap: ARTIST_GRID_GAP_PX }}
            >
              {filteredArtists.map((a) => {
                const on = selectedIds.has(a.id)
                return (
                  <AnimatedPressable
                    key={a.id}
                    onPress={() => toggleArtist(a.id)}
                    style={{ width: artistTileWidth }}
                    className={`rounded-xl border px-4 py-3.5 ${
                      on ? 'border-amber-accent bg-amber-accent/15' : 'border-wood-600/50 bg-wood-800/80'
                    }`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: on }}
                  >
                    <Text
                      className="font-sans-medium text-sm leading-snug text-cream"
                      numberOfLines={2}
                      ellipsizeMode="tail"
                    >
                      {a.name}
                    </Text>
                    <Text
                      className="mt-2 font-sans text-[10px] uppercase tracking-wide text-muted-brown"
                      numberOfLines={1}
                      ellipsizeMode="tail"
                    >
                      {a.styleTag}
                    </Text>
                  </AnimatedPressable>
                )
              })}
            </View>
          </ScrollView>
          <AnimatedPressable
            onPress={goNext}
            disabled={!canNextStep0}
            className={`mt-6 w-full rounded-lg px-4 py-3 ${canNextStep0 ? 'bg-amber-accent' : 'bg-wood-700'}`}
            accessibilityRole="button"
            accessibilityLabel="Continue to vibe step"
          >
            <Text
              className={`text-center font-sans-medium ${canNextStep0 ? 'text-wood-900' : 'text-muted-brown'}`}
            >
              Next
            </Text>
          </AnimatedPressable>
        </View>
      ) : null}

      {step === 1 ? (
        <View className="py-2">
          <Text className="text-center font-serif text-2xl text-cream">What&apos;s your vibe?</Text>
          <Text className="mt-2 text-center font-sans text-sm text-muted-brown">
            Four lanes — pick the one that feels closest today (icons are decorative).
          </Text>
          <View className="mt-6 gap-3">
            {TASTE_QUIZ_VIBE_CARDS.map((c) => {
              const on = vibe === c.id
              return (
                <AnimatedPressable
                  key={c.id}
                  onPress={() => setVibe(c.id)}
                  className={`flex-row items-center gap-3 rounded-xl border p-4 ${
                    on ? 'border-amber-accent bg-amber-accent/12' : 'border-wood-600/50 bg-wood-800/80'
                  }`}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                >
                  <View className="h-11 w-11 items-center justify-center rounded-full border border-wood-600/50 bg-wood-900/60">
                    <Music2 color={colors.amber.accent} size={22} strokeWidth={1.5} />
                  </View>
                  <View className="flex-1">
                    <Text className="font-sans-medium text-base text-cream">{c.title}</Text>
                    <Text className="mt-1 font-sans text-xs leading-5 text-muted-brown">{c.blurb}</Text>
                  </View>
                </AnimatedPressable>
              )
            })}
          </View>
          <AnimatedPressable
            onPress={goNext}
            disabled={!canNextStep1}
            className={`mt-8 w-full rounded-lg px-4 py-3 ${canNextStep1 ? 'bg-amber-accent' : 'bg-wood-700'}`}
            accessibilityRole="button"
          >
            <Text
              className={`text-center font-sans-medium ${canNextStep1 ? 'text-wood-900' : 'text-muted-brown'}`}
            >
              Next
            </Text>
          </AnimatedPressable>
        </View>
      ) : null}

      {step === 2 ? (
        <View className="py-2">
          <Text className="text-center font-serif text-2xl text-cream">How long have you played?</Text>
          <Text className="mt-2 text-center font-sans text-sm text-muted-brown">
            We&apos;ll seed skill weights from this — you can still refine them with real sessions.
          </Text>
          <View className="mt-6 gap-3">
            {EXPERIENCE_OPTIONS.map((o) => {
              const on = experience === o.id
              return (
                <AnimatedPressable
                  key={o.id}
                  onPress={() => setExperience(o.id)}
                  className={`rounded-xl border p-4 ${
                    on ? 'border-amber-accent bg-amber-accent/12' : 'border-wood-600/50 bg-wood-800/80'
                  }`}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                >
                  <View className="flex-row items-center gap-3">
                    <Guitar color={colors.amber.accent} size={22} strokeWidth={1.5} />
                    <View className="flex-1">
                      <Text className="font-sans-medium text-base text-cream">{o.title}</Text>
                      <Text className="mt-1 font-sans text-xs text-muted-brown">{o.blurb}</Text>
                    </View>
                  </View>
                </AnimatedPressable>
              )
            })}
          </View>
          <AnimatedPressable
            onPress={submit}
            disabled={!canSubmit || busy}
            className={`mt-8 w-full rounded-lg px-4 py-3 ${canSubmit && !busy ? 'bg-amber-accent' : 'bg-wood-700'}`}
            accessibilityRole="button"
            accessibilityLabel="Save preferences and continue"
          >
            <Text
              className={`text-center font-sans-medium ${canSubmit && !busy ? 'text-wood-900' : 'text-muted-brown'}`}
            >
              {busy ? 'Saving…' : 'Save and continue'}
            </Text>
          </AnimatedPressable>
        </View>
      ) : null}
    </OnboardingScreenShell>
  )
}

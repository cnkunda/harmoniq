import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { useCallback, useMemo, useState } from 'react'
import { Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { getLicks } from '@/src/db/client'
import type { LickRow } from '@/src/db/types'
import { useLessonStore } from '@/src/stores/lessonStore'

export default function LibraryScreen() {
  const router = useRouter()
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const [licks, setLicks] = useState<LickRow[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [songFilter, setSongFilter] = useState<string>('all')
  const [techniqueFilter, setTechniqueFilter] = useState<string>('all')
  const [transposeById, setTransposeById] = useState<Record<string, number>>({})

  const refresh = useCallback(() => {
    setLoadError(null)
    void getLicks()
      .then(setLicks)
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load licks.'))
  }, [])

  useFocusEffect(
    useCallback(() => {
      refresh()
    }, [refresh]),
  )

  const drill = useCallback(
    (lick: LickRow) => {
      const semitones = transposeById[lick.id] ?? 0
      saveLesson({
        job_id: `lick-${lick.id}`,
        song_title: lick.song_title ?? 'Saved lick',
        artist: lick.artist ?? undefined,
        key: lick.key ?? undefined,
        stems: {},
        beat_grid: [],
        bar_timestamps: [],
        lyrics_aligned: [],
        sections: [
          {
            label: lick.position ?? 'Lick',
            primary_position: lick.position ?? undefined,
            tab_full_gp5_base64: lick.tab_gp5_base64,
            transposition_semitones: semitones,
          },
        ],
      })
      setLessonSectionIndex(0)
      router.push('/session/study')
    },
    [router, saveLesson, setLessonSectionIndex, transposeById],
  )

  const songOptions = useMemo(() => {
    const set = new Set<string>()
    for (const l of licks) {
      const s = l.song_title?.trim()
      if (s) set.add(s)
    }
    return ['all', ...Array.from(set).sort((a, b) => a.localeCompare(b))]
  }, [licks])

  const techniqueOptions = useMemo(() => {
    const set = new Set<string>()
    for (const l of licks) {
      for (const t of l.technique_tags ?? []) {
        const s = t.trim()
        if (s) set.add(s)
      }
    }
    return ['all', ...Array.from(set).sort((a, b) => a.localeCompare(b))]
  }, [licks])

  const filteredLicks = useMemo(
    () =>
      licks.filter((l) => {
        const bySong = songFilter === 'all' || (l.song_title?.trim() ?? '') === songFilter
        const byTechnique = techniqueFilter === 'all' || (l.technique_tags ?? []).includes(techniqueFilter)
        return bySong && byTechnique
      }),
    [licks, songFilter, techniqueFilter],
  )

  const empty = useMemo(() => filteredLicks.length === 0 && !loadError, [filteredLicks.length, loadError])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 28 }}>
        <View className="flex-row items-center justify-between">
          <Text className="font-serif text-2xl text-cream">Library</Text>
          <Pressable onPress={() => router.back()} accessibilityRole="button">
            <Text className="font-sans text-sm text-muted-brown">Back</Text>
          </Pressable>
        </View>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          Saved licks from Review. Drill opens directly in Study with the same tab payload.
        </Text>

        <View className="mt-4 gap-3">
          <View>
            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-light">Song filter</Text>
            <View className="flex-row flex-wrap gap-2">
              {songOptions.map((s) => (
                <Pressable
                  key={`song-${s}`}
                  onPress={() => setSongFilter(s)}
                  className={`rounded-full border px-3 py-1.5 ${
                    songFilter === s ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/35'
                  }`}
                >
                  <Text className={`font-sans text-xs ${songFilter === s ? 'text-wood-900' : 'text-muted-brown'}`}>
                    {s === 'all' ? 'All songs' : s}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>

          <View>
            <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-light">Technique filter</Text>
            <View className="flex-row flex-wrap gap-2">
              {techniqueOptions.map((t) => (
                <Pressable
                  key={`tech-${t}`}
                  onPress={() => setTechniqueFilter(t)}
                  className={`rounded-full border px-3 py-1.5 ${
                    techniqueFilter === t
                      ? 'border-amber-accent bg-amber-accent/20'
                      : 'border-wood-600/45 bg-cream-dark/35'
                  }`}
                >
                  <Text className={`font-sans text-xs ${techniqueFilter === t ? 'text-wood-900' : 'text-muted-brown'}`}>
                    {t === 'all' ? 'All techniques' : t}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        </View>

        {loadError ? (
          <View className="mt-6 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2">
            <Text className="font-sans text-sm text-danger">{loadError}</Text>
          </View>
        ) : null}

        {empty ? (
          <View className="mt-8 rounded-xl border border-wood-600/50 bg-wood-800/70 px-4 py-4">
            <Text className="font-sans text-sm text-cream">No saved licks yet.</Text>
            <Text className="mt-1 font-sans text-xs text-muted-brown">
              Run a review, then tap "Save to Library."
            </Text>
          </View>
        ) : null}

        <View className="mt-6 gap-3">
          {filteredLicks.map((lick) => (
            <View key={lick.id} className="rounded-xl border border-wood-600/45 bg-wood-800/80 px-4 py-4">
              <Text className="font-sans-medium text-sm text-cream">{lick.song_title ?? 'Untitled lick'}</Text>
              <Text className="mt-1 font-sans text-xs text-muted-brown">
                {lick.artist ?? 'Unknown artist'} · {lick.position ?? 'Position n/a'} · {new Date(lick.date_saved).toLocaleDateString()}
              </Text>
              {lick.coach_oneliner ? (
                <Text className="mt-2 font-sans text-xs text-muted-brown" numberOfLines={2}>
                  {lick.coach_oneliner}
                </Text>
              ) : null}
              <View className="mt-3 flex-row items-center gap-2">
                {[-2, -1, 0, 1, 2].map((n) => {
                  const selected = (transposeById[lick.id] ?? 0) === n
                  return (
                    <Pressable
                      key={`${lick.id}-tp-${n}`}
                      onPress={() =>
                        setTransposeById((prev) => ({
                          ...prev,
                          [lick.id]: n,
                        }))
                      }
                      className={`rounded-full border px-2.5 py-1 ${
                        selected ? 'border-amber-accent bg-amber-accent/25' : 'border-wood-600/45 bg-cream-dark/35'
                      }`}
                    >
                      <Text className={`font-mono text-[11px] ${selected ? 'text-wood-900' : 'text-muted-brown'}`}>
                        {n > 0 ? `+${n}` : n}
                      </Text>
                    </Pressable>
                  )
                })}
                <Text className="font-sans text-xs text-muted-brown">Transpose (semitones)</Text>
              </View>

              <Pressable
                onPress={() => drill(lick)}
                className="mt-3 self-start rounded-lg bg-amber-accent px-3 py-2"
                accessibilityRole="button"
              >
                <Text className="font-sans-medium text-wood-900">Drill this</Text>
              </Pressable>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}

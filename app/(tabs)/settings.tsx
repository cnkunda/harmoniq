import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import * as FileSystem from 'expo-file-system/legacy'
import * as Sharing from 'expo-sharing'
import { useCallback, useEffect, useState } from 'react'
import Slider from '@react-native-community/slider'
import {
  Alert,
  Platform,
  Pressable,
  ScrollView,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { FormCheckbox } from '@/components/FormCheckbox'
import { toast } from '@/components/ToastConfig'
import { disconnectSpotifyServer, fetchSpotifyTasteProfile, parseTasteProfileJson } from '@/src/api/analyze'
import { stop as stopVoiceCoach } from '@/src/audio/voiceCoach'
import { hydrateVoiceCoachPrefs } from '@/src/audio/hydrateVoiceCoachPrefs'
import {
  buildJournalExportText,
  clearAllPracticeData,
  getAppPref,
  setAppPref,
} from '@/src/db/client'
import {
  COACH_VOICE_OPTIONS,
  PREF_COACH_VOICE,
  PREF_EXPERIENCE_LEVEL,
  PREF_METRONOME_DEFAULT_ON,
  PREF_MOOD_CHECK_SKIP,
  PREF_PREFER_SIMPLER_TABS,
  PREF_SPOTIFY_CLIENT_SESSION,
  PREF_SPOTIFY_TASTE_PROFILE_JSON,
  PREF_TASTE_PROFILE_JSON,
  PREF_STANDARD_TUNING_HZ,
  PREF_STYLE_FOCUS,
  PREF_VOICE_COACH_ENABLED,
  PREF_VOICE_COACH_GENDER,
  PREF_VOICE_COACH_RATE,
  type CoachVoiceId,
} from '@/src/db/schema'
import { runSpotifyConnect } from '@/src/spotify/connectSpotify'
import { fetchPersistAndDeriveSpotifyTaste } from '@/src/spotify/fetchPersistAndDeriveSpotify'
import { formatSpotifySetupError } from '@/src/spotify/spotifyConnectErrors'
import type { SpotifyTasteProfile } from '@/src/types'
import { useSkillStore } from '@/src/stores/skillStore'
import type { VoiceGenderPref } from '@/src/stores/voiceCoachPrefsStore'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'

function isCoachVoice(s: string): s is CoachVoiceId {
  return (COACH_VOICE_OPTIONS as readonly string[]).includes(s)
}

function parseStoredSpotifyProfile(raw: string | null): SpotifyTasteProfile | null {
  if (!raw || !raw.trim()) return null
  try {
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return null
    const rec = o as Record<string, unknown>
    const top_genres = Array.isArray(rec.top_genres) ? rec.top_genres.filter((x) => typeof x === 'string') : []
    const top_artists = Array.isArray(rec.top_artists) ? rec.top_artists.filter((x) => typeof x === 'string') : []
    const energy_avg = typeof rec.energy_avg === 'number' && Number.isFinite(rec.energy_avg) ? rec.energy_avg : 0
    const tempo_avg = typeof rec.tempo_avg === 'number' && Number.isFinite(rec.tempo_avg) ? rec.tempo_avg : 0
    const instrumentalness_avg =
      typeof rec.instrumentalness_avg === 'number' && Number.isFinite(rec.instrumentalness_avg)
        ? rec.instrumentalness_avg
        : 0
    return { top_genres, top_artists, energy_avg, tempo_avg, instrumentalness_avg }
  } catch {
    return null
  }
}

export default function SettingsScreen() {
  const router = useRouter()
  const skipTuneStep = useSessionPrefsStore((s) => s.skipTuneStep)
  const setSkipTuneStep = useSessionPrefsStore((s) => s.setSkipTuneStep)
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const resetLesson = useLessonStore((s) => s.resetLesson)
  const clearAnnotations = useSessionAnnotationsStore((s) => s.clearAll)

  const [preferSimplerTabs, setPreferSimplerTabs] = useState(false)
  const [tuningHz, setTuningHz] = useState('440')
  const [styleFocus, setStyleFocus] = useState('')
  const [metronomeDefaultOn, setMetronomeDefaultOn] = useState(true)
  const [skipMoodCheck, setSkipMoodCheck] = useState(false)
  const [coachVoice, setCoachVoice] = useState<CoachVoiceId>('warm')
  const [voiceCoachEnabled, setVoiceCoachEnabled] = useState(true)
  const [voiceCoachRate, setVoiceCoachRate] = useState(1)
  const [voiceCoachGender, setVoiceCoachGender] = useState<VoiceGenderPref>('default')
  const [exportBusy, setExportBusy] = useState(false)
  const [spotifyProfile, setSpotifyProfile] = useState<SpotifyTasteProfile | null>(null)
  const [derivedTasteLabel, setDerivedTasteLabel] = useState<string | null>(null)
  const [experienceLevelSaved, setExperienceLevelSaved] = useState<string | null>(null)

  const loadPrefs = useCallback(async () => {
    const [simpler, hz, style, metro, skipMood, voice, tasteJson, derivedTasteRaw, expSaved] = await Promise.all([
      getAppPref(PREF_PREFER_SIMPLER_TABS),
      getAppPref(PREF_STANDARD_TUNING_HZ),
      getAppPref(PREF_STYLE_FOCUS),
      getAppPref(PREF_METRONOME_DEFAULT_ON),
      getAppPref(PREF_MOOD_CHECK_SKIP),
      getAppPref(PREF_COACH_VOICE),
      getAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON),
      getAppPref(PREF_TASTE_PROFILE_JSON),
      getAppPref(PREF_EXPERIENCE_LEVEL),
    ])
    setPreferSimplerTabs(simpler === '1')
    setTuningHz(hz && hz.trim() ? hz : '440')
    setStyleFocus(style ?? '')
    setMetronomeDefaultOn(metro !== '0')
    setSkipMoodCheck(skipMood === '1')
    const vRaw = voice ?? ''
    setCoachVoice(isCoachVoice(vRaw) ? vRaw : 'warm')
    setSpotifyProfile(parseStoredSpotifyProfile(tasteJson))
    const dt = parseTasteProfileJson(derivedTasteRaw)
    setDerivedTasteLabel(dt?.style_label?.trim() ? dt.style_label.trim() : null)
    const ex = expSaved?.trim().toLowerCase()
    setExperienceLevelSaved(ex === 'beginner' || ex === 'intermediate' || ex === 'advanced' ? ex : null)
    await hydrateVoiceCoachPrefs()
    const vc = useVoiceCoachPrefsStore.getState()
    setVoiceCoachEnabled(vc.enabled)
    setVoiceCoachRate(vc.rate)
    setVoiceCoachGender(vc.gender)
  }, [])

  useFocusEffect(
    useCallback(() => {
      void loadPrefs()
    }, [loadPrefs]),
  )

  useFocusEffect(
    useCallback(() => {
      if (Platform.OS !== 'web' || typeof window === 'undefined') return
      const sp = new URLSearchParams(window.location.search)
      const oauth = sp.get('spotify_oauth')
      const cs = (sp.get('client_session') ?? '').trim()
      if (oauth === '1' && cs) {
        window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`)
        void (async () => {
          try {
            const profile = await fetchPersistAndDeriveSpotifyTaste(cs)
            setSpotifyProfile(profile)
            await loadSkills()
            await loadPrefs()
            toast.success('Spotify connected.')
          } catch (e) {
            toast.error(formatSpotifySetupError(e))
          }
        })()
        return
      }
      if (oauth === '0' || sp.get('spotify_error') === '1') {
        window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`)
        toast.error('Spotify authorization was cancelled or failed.')
      }
    }, [loadPrefs, loadSkills]),
  )

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const cs = (await getAppPref(PREF_SPOTIFY_CLIENT_SESSION))?.trim() ?? ''
      const raw = await getAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON)
      const local = parseStoredSpotifyProfile(raw)
      if (!cs || !local) return
      try {
        const fresh = await fetchSpotifyTasteProfile(cs)
        if (!cancelled) {
          await setAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON, JSON.stringify(fresh))
          setSpotifyProfile(fresh)
        }
      } catch {
        // Keep cached taste when Spotify or backend is unavailable (PRIORITIES §67).
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const persistSimpler = async (v: boolean) => {
    setPreferSimplerTabs(v)
    await setAppPref(PREF_PREFER_SIMPLER_TABS, v ? '1' : '0')
  }

  const persistTuning = async () => {
    const n = Number.parseFloat(tuningHz)
    if (!Number.isFinite(n) || n < 420 || n > 460) {
      toast.error('Tuning A4: use a number between 420 and 460 Hz.')
      return
    }
    await setAppPref(PREF_STANDARD_TUNING_HZ, String(n))
    toast.success('Reference pitch saved.')
  }

  const persistStyle = async () => {
    await setAppPref(PREF_STYLE_FOCUS, styleFocus.trim())
    toast.success('Style focus saved.')
  }

  const persistMetronome = async (v: boolean) => {
    setMetronomeDefaultOn(v)
    await setAppPref(PREF_METRONOME_DEFAULT_ON, v ? '1' : '0')
  }

  const persistSkipMoodCheck = async (v: boolean) => {
    setSkipMoodCheck(v)
    await setAppPref(PREF_MOOD_CHECK_SKIP, v ? '1' : '0')
  }

  const persistVoice = async (v: CoachVoiceId) => {
    setCoachVoice(v)
    await setAppPref(PREF_COACH_VOICE, v)
  }

  const persistVoiceCoachEnabled = async (v: boolean) => {
    setVoiceCoachEnabled(v)
    await setAppPref(PREF_VOICE_COACH_ENABLED, v ? '1' : '0')
    useVoiceCoachPrefsStore.getState().setAll({ enabled: v })
    if (!v) stopVoiceCoach()
  }

  const persistVoiceCoachRate = async (v: number) => {
    const clamped = Math.max(0.7, Math.min(1.2, v))
    setVoiceCoachRate(clamped)
    await setAppPref(PREF_VOICE_COACH_RATE, String(clamped))
    useVoiceCoachPrefsStore.getState().setAll({ rate: clamped })
  }

  const persistVoiceCoachGender = async (g: VoiceGenderPref) => {
    setVoiceCoachGender(g)
    await setAppPref(PREF_VOICE_COACH_GENDER, g)
    useVoiceCoachPrefsStore.getState().setAll({ gender: g })
  }

  const exportJournal = async () => {
    setExportBusy(true)
    try {
      const text = await buildJournalExportText()
      const stamp = new Date().toISOString().slice(0, 10)
      const fileName = `harmoniq-journal-${stamp}.txt`
      if (Platform.OS === 'web') {
        if (typeof document === 'undefined' || typeof Blob === 'undefined') {
          toast.error('Export is not available in this environment.')
          return
        }
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = fileName
        a.rel = 'noopener'
        a.click()
        URL.revokeObjectURL(url)
        toast.success('Download started.')
        return
      }
      const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
      if (!dir) throw new Error('No writable directory')
      const path = `${dir}${fileName}`
      await FileSystem.writeAsStringAsync(path, text, { encoding: FileSystem.EncodingType.UTF8 })
      const canShare = await Sharing.isAvailableAsync()
      if (!canShare) {
        toast.success(`Saved to ${path}`)
        return
      }
      await Sharing.shareAsync(path, { mimeType: 'text/plain', dialogTitle: 'Export journal' })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExportBusy(false)
    }
  }

  const runClearPracticeData = () => {
    void (async () => {
      try {
        await clearAllPracticeData()
        resetLesson()
        clearAnnotations()
        await loadSkills()
        toast.success('Local practice data cleared.')
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Clear failed')
      }
    })()
  }

  const connectSpotify = () => {
    void runSpotifyConnect({ onProfile: setSpotifyProfile })
  }

  const disconnectSpotify = () => {
    void (async () => {
      try {
        const cs = (await getAppPref(PREF_SPOTIFY_CLIENT_SESSION))?.trim() ?? ''
        if (cs) {
          try {
            await disconnectSpotifyServer(cs)
          } catch {
            // Still clear local prefs so the UI matches user intent.
          }
        }
        await setAppPref(PREF_SPOTIFY_CLIENT_SESSION, '')
        await setAppPref(PREF_SPOTIFY_TASTE_PROFILE_JSON, '')
        setSpotifyProfile(null)
        toast.success('Spotify disconnected.')
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Disconnect failed')
      }
    })()
  }

  const confirmClear = () => {
    const detail =
      'Sessions, licks, jam history, and skill progress will be removed. Section annotations and the loaded lesson are cleared. Settings on this screen are kept.'
    if (Platform.OS === 'web') {
      if (typeof window !== 'undefined' && window.confirm(`Clear all practice data?\n\n${detail}`)) {
        runClearPracticeData()
      }
      return
    }
    Alert.alert('Clear all practice data?', detail, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear', style: 'destructive', onPress: runClearPracticeData },
    ])
  }

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 40 }}>
        <Text className="font-serif text-2xl text-cream">Settings</Text>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          Preferences are stored on this device. Coach voice is saved for a future API prompt style.
        </Text>

        <View className="mt-8 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Practice</Text>
          <View className="mt-4 flex-row items-center justify-between gap-3">
            <View className="flex-1 pr-2">
              <Text className="font-sans-medium text-sm text-cream">Prefer simpler tabs when analysis is uncertain</Text>
              <Text className="mt-1 font-sans text-[11px] text-muted-brown">
                Uses skeleton (or alt) tab by default on Study when transcription confidence is low. Reload section or
                return to Study to apply.
              </Text>
            </View>
            <Switch value={preferSimplerTabs} onValueChange={(v) => void persistSimpler(v)} />
          </View>
          <View className="mt-5 border-t border-wood-600/35 pt-5">
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Session start</Text>
            <Text className="mt-2 font-sans text-[11px] text-muted-brown">
              When enabled, new sessions open on Listen and skip mic calibration and the low-E check.
            </Text>
            <View className="mt-3">
              <FormCheckbox
                checked={skipTuneStep}
                onCheckedChange={(v) => void setSkipTuneStep(v)}
                label="Don't show this again — skip tune & room noise before future lessons."
                labelClassName="text-cream"
                surface="wood"
              />
            </View>
            <View className="mt-4 flex-row items-center justify-between gap-3">
              <Text className="flex-1 font-sans text-sm text-cream">Auto-skip daily mood check before sessions</Text>
              <Switch value={skipMoodCheck} onValueChange={(v) => void persistSkipMoodCheck(v)} />
            </View>
          </View>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Tuning</Text>
          <Text className="mt-2 font-sans text-xs text-muted-brown">A4 reference (Hz) — for future tuner features.</Text>
          <TextInput
            value={tuningHz}
            onChangeText={setTuningHz}
            keyboardType="decimal-pad"
            className="mt-2 rounded-lg border border-wood-600/50 bg-ivory/95 px-3 py-2 font-mono text-sm text-wood-900"
            placeholder="440"
          />
          <Pressable
            onPress={() => void persistTuning()}
            className="mt-3 self-start rounded-lg bg-amber-accent/90 px-4 py-2"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-sm text-wood-900">Save tuning</Text>
          </Pressable>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Style focus</Text>
          <Text className="mt-2 font-sans text-xs text-muted-brown">Short note (blues, fingerstyle, etc.) for future coach context.</Text>
          <TextInput
            value={styleFocus}
            onChangeText={setStyleFocus}
            className="mt-2 rounded-lg border border-wood-600/50 bg-ivory/95 px-3 py-2 font-sans text-sm text-wood-900"
            placeholder="e.g. slow blues phrasing"
          />
          <Pressable
            onPress={() => void persistStyle()}
            className="mt-3 self-start rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-sm text-wood-900">Save style focus</Text>
          </Pressable>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Metronome</Text>
          <View className="mt-3 flex-row items-center justify-between">
            <Text className="flex-1 font-sans text-sm text-cream">Default metronome on (Slow / Play)</Text>
            <Switch value={metronomeDefaultOn} onValueChange={(v) => void persistMetronome(v)} />
          </View>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Voice coach</Text>
          <Text className="mt-2 font-sans text-xs text-muted-brown">
            Reads coach notes at session steps, practice-plan slots, and quick feedback after Play — interruptible when
            you move on.
          </Text>
          <View className="mt-3 flex-row items-center justify-between">
            <Text className="flex-1 font-sans text-sm text-cream">Speak coach notes aloud</Text>
            <Switch value={voiceCoachEnabled} onValueChange={(v) => void persistVoiceCoachEnabled(v)} />
          </View>
          <Text className="mt-4 font-sans text-sm text-cream">Speech rate</Text>
          <Text className="mt-1 font-sans text-[11px] text-muted-brown">0.7 (slower) — 1.2 (faster)</Text>
          <Slider
            style={{ width: '100%', height: 36, marginTop: 8 }}
            minimumValue={0.7}
            maximumValue={1.2}
            step={0.05}
            value={voiceCoachRate}
            minimumTrackTintColor="#D4A574"
            maximumTrackTintColor="#5C4535"
            thumbTintColor="#E8B86D"
            onValueChange={setVoiceCoachRate}
            onSlidingComplete={(v) => void persistVoiceCoachRate(v)}
          />
          <Text className="mt-2 font-sans text-xs text-muted-brown">Current: {voiceCoachRate.toFixed(2)}</Text>
          <Text className="mt-4 font-sans text-sm text-cream">Voice character (where supported)</Text>
          <View className="mt-2 flex-row flex-wrap gap-2">
            {(['default', 'female', 'male'] as const).map((g) => (
              <AnimatedPressable
                key={g}
                haptic="light"
                onPress={() => void persistVoiceCoachGender(g)}
                className={`rounded-full border px-3 py-1.5 ${
                  voiceCoachGender === g ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/45 bg-cream-dark/40'
                }`}
                accessibilityRole="button"
                accessibilityState={{ selected: voiceCoachGender === g }}
              >
                <Text className={`font-sans text-xs capitalize ${voiceCoachGender === g ? 'text-wood-900' : 'text-cream'}`}>
                  {g}
                </Text>
              </AnimatedPressable>
            ))}
          </View>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Music preferences</Text>
          <Text className="mt-2 font-sans text-xs text-muted-brown">
            Three steps—artists you love, vibe, and experience. Redo anytime; sessions and your library stay as they are.
            Experience sets how we weight skills until real practice data comes in.
          </Text>
          {experienceLevelSaved ? (
            <Text className="mt-2 font-sans text-sm text-cream">
              Saved experience:{' '}
              <Text className="font-sans-medium capitalize text-amber-light">{experienceLevelSaved}</Text>
            </Text>
          ) : (
            <Text className="mt-2 font-sans text-sm text-muted-brown">
              Experience not saved yet—finish the style quiz once so the coach can meet you where you are.
            </Text>
          )}
          {derivedTasteLabel ? (
            <Text className="mt-2 font-sans text-sm text-cream">
              Style lane: <Text className="font-sans-medium text-amber-light">{derivedTasteLabel}</Text>
            </Text>
          ) : (
            <Text className="mt-2 font-sans text-sm text-muted-brown">No saved style preferences yet.</Text>
          )}
          <AnimatedPressable
            onPress={() => router.push('/onboarding/taste-quiz?update=1')}
            className="mt-4 self-start rounded-lg border border-wood-600/50 bg-wood-900/40 px-4 py-2"
            accessibilityRole="button"
            accessibilityLabel="Update music preferences with style quiz"
          >
            <Text className="font-sans-medium text-sm text-cream">Update preferences</Text>
          </AnimatedPressable>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Spotify</Text>
          <Text className="mt-2 font-sans text-xs text-muted-brown">
            Connect Spotify so Harmoniq can read top artists, genres, and recent listening (tokens stay on the
            server).
          </Text>
          <View className="mt-3 flex-row flex-wrap items-center gap-2">
            <Text className="font-sans text-sm text-cream">
              {spotifyProfile !== null ? 'Spotify · Connected' : 'Not connected'}
            </Text>
          </View>
          {spotifyProfile !== null &&
            (spotifyProfile.top_artists.length > 0 || spotifyProfile.top_genres.length > 0) && (
              <Text className="mt-2 font-sans text-[11px] leading-4 text-muted-brown" numberOfLines={4}>
                {spotifyProfile.top_artists.slice(0, 5).join(' · ')}
                {spotifyProfile.top_genres.length > 0
                  ? `\n${spotifyProfile.top_genres.slice(0, 6).join(', ')}`
                  : ''}
              </Text>
            )}
          <View className="mt-4 flex-row flex-wrap gap-2">
            <AnimatedPressable
              onPress={connectSpotify}
              className="rounded-lg bg-amber-accent/90 px-4 py-2"
              accessibilityRole="button"
            >
              <Text className="font-sans-medium text-sm text-wood-900">Connect Spotify</Text>
            </AnimatedPressable>
            <AnimatedPressable
              onPress={disconnectSpotify}
              className="rounded-lg border border-wood-600/50 bg-wood-900/40 px-4 py-2"
              accessibilityRole="button"
            >
              <Text className="font-sans-medium text-sm text-cream">Disconnect</Text>
            </AnimatedPressable>
          </View>
        </View>

        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Coach voice</Text>
          <Text className="mt-1 font-sans text-[11px] text-muted-brown">Stored for a later server prompt variant.</Text>
          <View className="mt-3 flex-row flex-wrap gap-2">
            {COACH_VOICE_OPTIONS.map((v) => (
              <Pressable
                key={v}
                onPress={() => void persistVoice(v)}
                className={`rounded-full border px-3 py-1.5 ${
                  coachVoice === v ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/50 bg-wood-900/40'
                }`}
                accessibilityRole="button"
                accessibilityState={{ selected: coachVoice === v }}
              >
                <Text className={`font-sans text-xs capitalize ${coachVoice === v ? 'text-amber-light' : 'text-cream'}`}>
                  {v}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View className="mt-6 gap-3">
          <Pressable
            onPress={() => void exportJournal()}
            disabled={exportBusy}
            className="rounded-lg border border-amber-accent/50 bg-amber-accent/15 px-4 py-3 disabled:opacity-50"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-amber-light">
              {exportBusy ? 'Preparing export…' : 'Export journal (plain text)'}
            </Text>
          </Pressable>
          <Pressable
            onPress={confirmClear}
            className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3"
            accessibilityRole="button"
          >
            <Text className="text-center font-sans-medium text-danger">Clear all practice data…</Text>
          </Pressable>
        </View>

        <Pressable
          onPress={() => router.back()}
          className="mt-8 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
        >
          <Text className="text-center font-sans-medium text-wood-900">Back</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  )
}

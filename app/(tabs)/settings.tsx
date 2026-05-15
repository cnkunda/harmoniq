import { useFocusEffect } from '@react-navigation/native'
import * as FileSystem from 'expo-file-system/legacy'
import { useRouter } from 'expo-router'
import * as Sharing from 'expo-sharing'
import {
  ChevronRight,
  Database,
  Download,
  Guitar,
  Link2,
  Music,
  Settings as SettingsIcon,
  Sliders,
  Trash2,
  User,
} from 'lucide-react-native'
import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Platform,
  ScrollView,
  Text,
  TextInput,
  View
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { FormCheckbox } from '@/components/FormCheckbox'
import {
  SettingsCard,
  SettingsChips,
  SettingsSection,
  SettingsSegmented,
  SettingsSlider,
  SettingsSwitch,
} from '@/components/settings'
import { toast } from '@/components/ToastConfig'
import { disconnectSpotifyServer, fetchSpotifyTasteProfile, parseTasteProfileJson } from '@/src/api/analyze'
import { hydrateVoiceCoachPrefs } from '@/src/audio/hydrateVoiceCoachPrefs'
import { stop as stopVoiceCoach } from '@/src/audio/voiceCoach'
import colors from '@/src/constants/colors'
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
  PREF_STANDARD_TUNING_HZ,
  PREF_STYLE_FOCUS,
  PREF_TASTE_PROFILE_JSON,
  PREF_VOICE_COACH_ENABLED,
  PREF_VOICE_COACH_GENDER,
  PREF_VOICE_COACH_RATE,
  type CoachVoiceId,
} from '@/src/db/schema'
import { runSpotifyConnect } from '@/src/spotify/connectSpotify'
import { fetchPersistAndDeriveSpotifyTaste } from '@/src/spotify/fetchPersistAndDeriveSpotify'
import { formatSpotifySetupError } from '@/src/spotify/spotifyConnectErrors'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import { useSkillStore } from '@/src/stores/skillStore'
import type { VoiceGenderPref } from '@/src/stores/voiceCoachPrefsStore'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'
import type { SpotifyTasteProfile } from '@/src/types'

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
  const user = useSkillStore((s) => s.nodes)
  const sessionsCount = 0 // TODO: Get from store when available

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
        {/* Header */}
        <View className="mb-6">
          <Text className="font-serif text-3xl text-cream">Settings</Text>
          <Text className="mt-2 font-sans text-sm text-muted-brown">
            Customize your practice experience
          </Text>
        </View>

        {/* User Profile Card */}
        <SettingsCard
          title="Your Profile"
          description="Track your progress and customize your experience"
          icon={User}
          variant="gradient"
        >
          <View className="mt-4 flex-row items-center gap-4">
            <View className="h-16 w-16 items-center justify-center rounded-full bg-wood-800/60 border border-wood-600">
              <User color={colors.amber.accent} size={32} strokeWidth={2} />
            </View>
            <View className="flex-1">
              <Text className="font-serif text-lg text-cream">Guitarist</Text>
              {experienceLevelSaved ? (
                <Text className="mt-1 font-sans text-sm text-amber-light/80 capitalize">
                  {experienceLevelSaved} player
                </Text>
              ) : (
                <Text className="mt-1 font-sans text-sm text-muted-brown">
                  Experience level not set
                </Text>
              )}
            </View>
          </View>
          <View className="mt-4 flex-row gap-4">
            <View className="flex-1 rounded-lg bg-wood-900/40 border border-wood-600/50 p-3">
              <Text className="font-sans text-2xl font-serif text-amber-light">{user.length}</Text>
              <Text className="mt-1 font-sans text-xs text-muted-brown uppercase tracking-wider">
                Skills
              </Text>
            </View>
            <View className="flex-1 rounded-lg bg-wood-900/40 border border-wood-600/50 p-3">
              <Text className="font-sans text-2xl font-serif text-amber-light">{sessionsCount}</Text>
              <Text className="mt-1 font-sans text-xs text-muted-brown uppercase tracking-wider">
                Sessions
              </Text>
            </View>
          </View>
        </SettingsCard>

        {/* Practice Settings */}
        <SettingsSection
          icon={Guitar}
          title="Practice Settings"
          description="Customize how you learn and practice"
          defaultOpen={true}
        >
          <SettingsSwitch
            label="Prefer simpler tabs"
            description="Uses skeleton tab when transcription confidence is low"
            value={preferSimplerTabs}
            onValueChange={(v) => void persistSimpler(v)}
          />
          <View className="mt-4 border-t border-wood-600/35 pt-4">
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light mb-3">
              Session Start
            </Text>
            <FormCheckbox
              checked={skipTuneStep}
              onCheckedChange={(v) => void setSkipTuneStep(v)}
              label="Skip tuning & room noise before sessions"
              labelClassName="text-cream"
              surface="wood"
            />
            <SettingsSwitch
              label="Auto-skip daily mood check"
              description="Skip mood check before starting sessions"
              value={skipMoodCheck}
              onValueChange={(v) => void persistSkipMoodCheck(v)}
            />
          </View>
        </SettingsSection>

        {/* Tuning Settings */}
        <SettingsSection
          icon={Sliders}
          title="Tuning"
          description="Reference pitch for tuner features"
          defaultOpen={false}
        >
          <Text className="font-sans text-xs text-muted-brown mb-2">A4 reference (Hz)</Text>
          <TextInput
            value={tuningHz}
            onChangeText={setTuningHz}
            keyboardType="decimal-pad"
            className="rounded-lg border border-wood-600/50 bg-ivory/95 px-3 py-2 font-mono text-sm text-wood-900"
            placeholder="440"
          />
          <AnimatedPressable
            onPress={() => void persistTuning()}
            haptic="light"
            className="mt-3 self-start rounded-lg bg-amber-accent/90 px-4 py-2"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-sm text-wood-900">Save tuning</Text>
          </AnimatedPressable>
        </SettingsSection>

        {/* Style Focus */}
        <SettingsSection
          icon={Music}
          title="Style Focus"
          description="Your musical preferences for coach context"
          defaultOpen={false}
        >
          <Text className="font-sans text-xs text-muted-brown mb-2">
            Short note (blues, fingerstyle, etc.)
          </Text>
          <TextInput
            value={styleFocus}
            onChangeText={setStyleFocus}
            className="rounded-lg border border-wood-600/50 bg-ivory/95 px-3 py-2 font-sans text-sm text-wood-900"
            placeholder="e.g. slow blues phrasing"
          />
          <AnimatedPressable
            onPress={() => void persistStyle()}
            haptic="light"
            className="mt-3 self-start rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-2"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-sm text-wood-900">Save style focus</Text>
          </AnimatedPressable>
        </SettingsSection>

        {/* Metronome */}
        <SettingsSection
          icon={SettingsIcon}
          title="Metronome"
          description="Default metronome behavior"
          defaultOpen={false}
        >
          <SettingsSwitch
            label="Default metronome on"
            description="Enable metronome by default in Slow and Play screens"
            value={metronomeDefaultOn}
            onValueChange={(v) => void persistMetronome(v)}
          />
        </SettingsSection>

        {/* Voice & Coach Settings */}
        <SettingsSection
          icon={Music}
          title="Voice & Coach Settings"
          description="Audio feedback and AI coach personality settings"
          defaultOpen={true}
        >
          <SettingsSwitch
            label="Speak coach notes aloud"
            description="Reads coach notes at each session phase and after Play"
            value={voiceCoachEnabled}
            onValueChange={(v) => void persistVoiceCoachEnabled(v)}
          />
          <SettingsSlider
            label="Speech rate"
            description="0.7 (slower) — 1.2 (faster)"
            value={voiceCoachRate}
            min={0.7}
            max={1.2}
            step={0.05}
            onValueChange={(v) => void persistVoiceCoachRate(v)}
            formatValue={(v) => v.toFixed(2)}
          />
          <SettingsSegmented
            label="Voice character"
            description="Where supported by the platform"
            options={['default', 'female', 'male'] as const}
            value={voiceCoachGender}
            onValueChange={(g) => void persistVoiceCoachGender(g as VoiceGenderPref)}
          />
          <View className="mt-4 border-t border-wood-600/35 pt-4">
            <SettingsChips
              label="Coach Voice Style"
              description="Prompt style for future AI coach variants"
              options={COACH_VOICE_OPTIONS}
              value={coachVoice}
              onValueChange={(v) => { if (isCoachVoice(v)) void persistVoice(v) }}
            />
          </View>
        </SettingsSection>

        {/* Music Preferences */}
        <SettingsSection
          icon={User}
          title="Music Preferences"
          description="Your musical taste and experience level"
          defaultOpen={true}
        >
          <View className="mb-4">
            {experienceLevelSaved ? (
              <Text className="font-sans text-sm text-cream">
                Experience:{' '}
                <Text className="font-sans-medium capitalize text-amber-light">{experienceLevelSaved}</Text>
              </Text>
            ) : (
              <Text className="font-sans text-sm text-muted-brown">
                Complete the style quiz to set your experience level
              </Text>
            )}
            {derivedTasteLabel ? (
              <Text className="mt-2 font-sans text-sm text-cream">
                Style lane: <Text className="font-sans-medium text-amber-light">{derivedTasteLabel}</Text>
              </Text>
            ) : (
              <Text className="mt-2 font-sans text-sm text-muted-brown">No style preferences saved yet</Text>
            )}
          </View>
          <AnimatedPressable
            onPress={() => router.push('/onboarding/taste-quiz?update=1')}
            haptic="medium"
            className="flex-row items-center justify-center gap-2 rounded-lg bg-amber-accent/90 px-4 py-3"
            accessibilityRole="button"
            accessibilityLabel="Update music preferences with style quiz"
          >
            <ChevronRight color={colors.wood[900]} size={18} strokeWidth={2} />
            <Text className="font-sans-medium text-sm text-wood-900">Update preferences</Text>
          </AnimatedPressable>
        </SettingsSection>

        {/* Spotify */}
        <SettingsSection
          icon={Link2}
          title="Spotify"
          description="Connect for personalized recommendations"
          defaultOpen={true}
        >
          <View className="mb-4">
            <Text className="font-sans text-sm text-cream">
              {spotifyProfile !== null ? 'Connected' : 'Not connected'}
            </Text>
            {spotifyProfile !== null &&
              (spotifyProfile.top_artists.length > 0 || spotifyProfile.top_genres.length > 0) && (
                <Text className="mt-2 font-sans text-[11px] leading-4 text-muted-brown" numberOfLines={4}>
                  {spotifyProfile.top_artists.slice(0, 5).join(' · ')}
                  {spotifyProfile.top_genres.length > 0
                    ? `\n${spotifyProfile.top_genres.slice(0, 6).join(', ')}`
                    : ''}
                </Text>
              )}
          </View>
          <View className="flex-row gap-2">
            <AnimatedPressable
              onPress={connectSpotify}
              haptic="medium"
              className="flex-1 rounded-lg bg-amber-accent/90 px-4 py-2.5"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-sm text-wood-900">Connect</Text>
            </AnimatedPressable>
            <AnimatedPressable
              onPress={disconnectSpotify}
              haptic="light"
              className="flex-1 rounded-lg border border-wood-600/50 bg-wood-900/40 px-4 py-2.5"
              accessibilityRole="button"
            >
              <Text className="text-center font-sans-medium text-sm text-cream">Disconnect</Text>
            </AnimatedPressable>
          </View>
        </SettingsSection>

        {/* Data Management */}
        <SettingsSection
          icon={Database}
          title="Data Management"
          description="Export or clear your practice data"
          defaultOpen={false}
        >
          <AnimatedPressable
            onPress={() => void exportJournal()}
            disabled={exportBusy}
            haptic="medium"
            className="mb-3 flex-row items-center justify-center gap-2 rounded-lg border border-amber-accent/50 bg-amber-accent/15 px-4 py-3 disabled:opacity-50"
            accessibilityRole="button"
          >
            <Download color={colors.amber.accent} size={18} strokeWidth={2} />
            <Text className="font-sans-medium text-amber-light">
              {exportBusy ? 'Preparing export…' : 'Export journal'}
            </Text>
          </AnimatedPressable>
          <AnimatedPressable
            onPress={confirmClear}
            haptic="heavy"
            className="flex-row items-center justify-center gap-2 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3"
            accessibilityRole="button"
          >
            <Trash2 color={colors.danger} size={18} strokeWidth={2} />
            <Text className="font-sans-medium text-danger">Clear all practice data…</Text>
          </AnimatedPressable>
        </SettingsSection>

        {/* Back Button */}
        <AnimatedPressable
          onPress={() => router.back()}
          haptic="light"
          className="mt-8 rounded-lg border border-wood-600/45 bg-cream-dark/45 px-4 py-3"
          accessibilityRole="button"
        >
          <Text className="text-center font-sans-medium text-wood-900">Back</Text>
        </AnimatedPressable>
      </ScrollView>
    </SafeAreaView>
  )
}

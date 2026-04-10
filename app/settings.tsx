import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import * as FileSystem from 'expo-file-system/legacy'
import * as Sharing from 'expo-sharing'
import { useCallback, useState } from 'react'
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

import { toast } from '@/components/ToastConfig'
import {
  buildJournalExportText,
  clearAllPracticeData,
  getAppPref,
  setAppPref,
} from '@/src/db/client'
import {
  COACH_VOICE_OPTIONS,
  PREF_COACH_VOICE,
  PREF_METRONOME_DEFAULT_ON,
  PREF_PREFER_SIMPLER_TABS,
  PREF_STANDARD_TUNING_HZ,
  PREF_STYLE_FOCUS,
  type CoachVoiceId,
} from '@/src/db/schema'
import { useSkillStore } from '@/src/stores/skillStore'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSessionAnnotationsStore } from '@/src/stores/sessionAnnotationsStore'

function isCoachVoice(s: string): s is CoachVoiceId {
  return (COACH_VOICE_OPTIONS as readonly string[]).includes(s)
}

export default function SettingsScreen() {
  const router = useRouter()
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const resetLesson = useLessonStore((s) => s.resetLesson)
  const clearAnnotations = useSessionAnnotationsStore((s) => s.clearAll)

  const [preferSimplerTabs, setPreferSimplerTabs] = useState(false)
  const [tuningHz, setTuningHz] = useState('440')
  const [styleFocus, setStyleFocus] = useState('')
  const [metronomeDefaultOn, setMetronomeDefaultOn] = useState(true)
  const [coachVoice, setCoachVoice] = useState<CoachVoiceId>('warm')
  const [exportBusy, setExportBusy] = useState(false)

  const loadPrefs = useCallback(async () => {
    const [simpler, hz, style, metro, voice] = await Promise.all([
      getAppPref(PREF_PREFER_SIMPLER_TABS),
      getAppPref(PREF_STANDARD_TUNING_HZ),
      getAppPref(PREF_STYLE_FOCUS),
      getAppPref(PREF_METRONOME_DEFAULT_ON),
      getAppPref(PREF_COACH_VOICE),
    ])
    setPreferSimplerTabs(simpler === '1')
    setTuningHz(hz && hz.trim() ? hz : '440')
    setStyleFocus(style ?? '')
    setMetronomeDefaultOn(metro !== '0')
    const vRaw = voice ?? ''
    setCoachVoice(isCoachVoice(vRaw) ? vRaw : 'warm')
  }, [])

  useFocusEffect(
    useCallback(() => {
      void loadPrefs()
    }, [loadPrefs]),
  )

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

  const persistVoice = async (v: CoachVoiceId) => {
    setCoachVoice(v)
    await setAppPref(PREF_COACH_VOICE, v)
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

  const confirmClear = () => {
    Alert.alert(
      'Clear all practice data?',
      'Sessions, licks, jam history, and skill progress will be removed. Section annotations and the loaded lesson are cleared. Settings on this screen are kept.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: () => {
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
          },
        },
      ],
    )
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

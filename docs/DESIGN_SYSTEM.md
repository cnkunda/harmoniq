# Harmoniq — Design System

> **React Native + Expo Edition**
> All components target **Expo SDK 51+, React Native, NativeWind v4, Expo Router v3**.
> The original Vite + react-router-dom web prototype is superseded by this file.
> See `PRIORITIES.md → Technology Resolution Notes` for the full migration rationale.

---

## Stack at a Glance

| Concern | Library |
|---|---|
| Framework | Expo managed workflow, SDK 51+ |
| Routing | Expo Router v3 (file-based, `app/` directory) |
| Styling | NativeWind v4 — Tailwind CSS on React Native |
| Animations | `react-native-reanimated` v3 |
| Icons | `lucide-react-native` (native + web) |
| State | Zustand (replaces mock store progressively) |
| DB — native | `expo-sqlite` |
| DB — web | IndexedDB (commit 38) |
| SVG | `react-native-svg` |
| Gradients | `expo-linear-gradient` → `WoodGradient` wrapper |
| Blur | `expo-blur` → `BlurView` |
| Audio | `expo-av` (`expo-audio` if SDK requires) |
| Tab rendering | AlphaTab via WebView harness (native) / DOM (web) |

**NativeWind note:** `className` works directly on `View`, `Text`, `Pressable`, `TextInput`, etc. in NativeWind v4. No `styled()` wrapper needed. Opacity color modifiers (`bg-wood-800/40`) require NativeWind v4 and colors defined as hex. CSS `grid` is not available in RN — use `flex-row flex-wrap` instead.

---

```tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        wood: {
          900: '#2C1810',
          800: '#3D2317',
          700: '#3D2B1F',
          600: '#4A3728',
          500: '#5C4535',
        },
        amber: {
          accent: '#D4A574',
          light: '#E8B86D',
        },
        cream: {
          DEFAULT: '#F5E6D0',
          dark:    '#EDE0CC',
        },
        ivory:   '#F5F0E8',
        muted: {
          brown: '#8B7D6B',
        },
        danger:  '#C17B5F',
        success: '#7A9B6D',
      },
      fontFamily: {
        serif:         ['PlayfairDisplay-Regular'],
        'serif-bold':  ['PlayfairDisplay-Bold'],
        'serif-italic':['PlayfairDisplay-Italic'],
        sans:          ['DMSans-Regular'],
        'sans-medium': ['DMSans-Medium'],
        mono:          ['JetBrainsMono-Regular'],
      },
    },
  },
  plugins: [],
}
```

```global.css
/* NativeWind v4 + Metro web: Tailwind v3 directives (ships in repo).
   `@import "nativewind/stylesheet"` alone can stall first web bundle on some setups. */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

```babel.config.js
// nativewind/babel is a preset (it returns { plugins: [...] }) — never put it in `plugins`.
// It already ends with react-native-worklets/plugin (Reanimated 4 aliases this from reanimated/plugin).
module.exports = function (api) {
  api.cache(true)
  return {
    presets: [
      ['babel-preset-expo', { jsxImportSource: 'nativewind' }],
      'nativewind/babel',
    ],
  }
}
```

```metro.config.js
const { getDefaultConfig } = require('expo/metro-config')
const { withNativeWind } = require('nativewind/metro')

const config = getDefaultConfig(__dirname)

module.exports = withNativeWind(config, { input: './global.css' })
```

---

```src/types/index.ts
// ── Lesson / Pipeline ──────────────────────────────────────────────

export interface LessonJSON {
  job_id:                    string
  song_title:                string
  artist:                    string
  key:                       string
  key_confidence:            number
  tempo:                     number
  tempo_confidence:          number
  transcription_confidence:  number
  beat_grid:                 number[]
  bar_timestamps:            number[]
  stems: {
    guitar:  string
    bass:    string
    drums:   string
    vocals:  string
    piano:   string
    other:   string
  }
  lyrics_aligned: LyricWord[]
  sections:       Section[]
}

export interface Section {
  label:                      string
  confidence:                 number
  start_bar:                  number
  end_bar:                    number
  start_time_seconds:         number
  end_time_seconds:           number
  technique_tags:             string[]
  tab_full_gp5_base64:        string
  tab_skeleton_gp5_base64:    string
  tab_alt_position_gp5_base64?: string
  midi_base64:                string
  primary_position:           string
  alt_position?:              string
  coach_note:                 string
  coach_explanation:          string
}

export interface LyricWord {
  word:          string
  time_seconds:  number
  bar:           number
  beat:          number
}

// ── Skill / SM-2 ───────────────────────────────────────────────────

export interface SkillNode {
  id:                string   // e.g. "bend_accuracy"
  label:             string
  score:             number   // 0.0–1.0
  sessions_count:    number
  last_session_date: string
  easiness_factor:   number   // SM-2
  interval_days:     number   // SM-2
  next_review_date:  string   // ISO date string
}

// ── Session / Lick / Jam ───────────────────────────────────────────

export interface Session {
  id:             string
  song_title:     string
  artist:         string
  section_label:  string
  /** Calendar day the session ended — **ISO `YYYY-MM-DD`** (parse with `T12:00:00` for local noon). Human strings like `"Yesterday"` are display-only and must not be the only stored value or date math breaks. */
  date:           string
  coach_review:   string
  pitch_accuracy: number
  phrasing_score: number
  nodes_targeted: string[]
  duration_min?:  number
}

export interface Annotation {
  bar:  number
  text: string
}

export interface Lick {
  id:                  string
  song_title:          string
  artist:              string
  key:                 string
  scale:               string
  position:            string
  tab_gp5_base64:      string
  audio_segment_path?: string
  coach_oneliner:      string
  technique_tags:      string[]
  user_annotations:    Annotation[]
  date_saved:          string
}

export interface JamSnapshot {
  id:                  string
  date:                string
  duration_seconds:    number
  scale_position_map:  Record<string, number>
  recurring_gestures:  string[]
  coach_summary:       string
}

// ── Scoring ────────────────────────────────────────────────────────

export interface ScoreResult {
  pitch_accuracy:        number
  note_duration_deltas:  number[]
  phrasing_score:        number
  bend_pitch_error_cents: number
  rushing_score:         number
  node_scores:           Record<string, number>
  waveform_comparison: {
    user_wav_base64:      string
    reference_wav_base64: string
  }
}

// ── API ────────────────────────────────────────────────────────────

export type JobStatus = 'processing' | 'complete' | 'failed'

export interface AnalyzeJob {
  job_id:  string
  status:  JobStatus
  result:  LessonJSON | null
  error:   string | null
}

// ── User / Prefs ───────────────────────────────────────────────────

export interface UserPrefs {
  name:                string
  guitar_type:         'Electric' | 'Acoustic' | 'Acoustic-electric'
  tuning:              string
  style_focus:         string[]
  coach_voice:         'Encouraging' | 'Direct' | 'Mixed'
  prefer_simpler_tabs: boolean
  metronome_default:   boolean
  onboarded:           boolean
}
```

---

```src/constants/colors.ts
const colors = {
  wood: {
    900: '#2C1810',
    800: '#3D2317',
    700: '#3D2B1F',
    600: '#4A3728',
    500: '#5C4535',
  },
  amber: {
    accent: '#D4A574',
    light:  '#E8B86D',
  },
  cream:   '#F5E6D0',
  ivory:   '#F5F0E8',
  muted: {
    brown: '#8B7D6B',
  },
  danger:  '#C17B5F',
  success: '#7A9B6D',
} as const

export default colors
```

---

```utils/mockData.ts
import type { LessonJSON, Session, Lick, SkillNode, JamSnapshot, UserPrefs } from '@/src/types'

export const MOCK_USER: UserPrefs = {
  name:                'Guitarist',
  guitar_type:         'Electric',
  tuning:              'Standard',
  style_focus:         ['Blues/Soul'],
  coach_voice:         'Mixed',
  prefer_simpler_tabs: false,
  metronome_default:   false,
  onboarded:           false,
}

export const MOCK_LESSONS: LessonJSON[] = [
  {
    job_id:                   'gravity-demo',
    song_title:               'Gravity',
    artist:                   'John Mayer',
    key:                      'G major',
    key_confidence:           0.92,
    tempo:                    72,
    tempo_confidence:         0.95,
    transcription_confidence: 0.81,
    beat_grid:                [0.0, 0.833, 1.667, 2.5],
    bar_timestamps:           [0.0, 3.33, 6.67, 10.0, 13.33],
    stems: {
      guitar: '/stems/guitar.wav',
      bass:   '/stems/bass.wav',
      drums:  '/stems/drums.wav',
      vocals: '/stems/vocals.wav',
      piano:  '/stems/piano.wav',
      other:  '/stems/other.wav',
    },
    lyrics_aligned: [
      { word: 'Gravity', time_seconds: 4.2, bar: 2, beat: 1 },
    ],
    sections: [
      {
        label:                      'Solo',
        confidence:                 0.81,
        start_bar:                  24,
        end_bar:                    32,
        start_time_seconds:         79.2,
        end_time_seconds:           105.6,
        technique_tags:             ['pre-bend', 'vibrato', 'phrasing'],
        tab_full_gp5_base64:        '',
        tab_skeleton_gp5_base64:    '',
        tab_alt_position_gp5_base64: undefined,
        midi_base64:                '',
        primary_position:           'pentatonic position 2',
        alt_position:               'pentatonic position 4',
        coach_note:                 'Mayer sits on the root note for a full beat before moving — that pause builds tension before the phrase resolves.',
        coach_explanation:          'The phrase works because the rest creates anticipation. The ear expects resolution, and Mayer delays it just long enough to make the landing feel earned.',
      },
    ],
  },
]

export const MOCK_SESSIONS: Session[] = [
  {
    id:             'sess1',
    song_title:     'Gravity',
    artist:         'John Mayer',
    section_label:  'Solo',
    date:           '2026-03-28',
    coach_review:   "You're rushing the end of the phrase. The pitch on the bend was great, but try holding that last note a full beat longer before releasing. Let it breathe.",
    pitch_accuracy: 0.78,
    phrasing_score: 0.55,
    nodes_targeted: ['bend_accuracy', 'phrasing'],
    duration_min:   18,
  },
  {
    id:             'sess2',
    song_title:     'Gravity',
    artist:         'John Mayer',
    section_label:  'Verse',
    date:           '2026-03-25',
    coach_review:   'We focused on playing slightly behind the beat. By the end of the session you were settling into the pocket nicely.',
    pitch_accuracy: 0.82,
    phrasing_score: 0.63,
    nodes_targeted: ['phrasing', 'timing'],
    duration_min:   22,
  },
]

export const MOCK_LICKS: Lick[] = [
  {
    id:                 'l1',
    song_title:         'Gravity',
    artist:             'John Mayer',
    key:                'G major',
    scale:              'G Major Pentatonic',
    position:           'Position 2',
    tab_gp5_base64:     '',
    coach_oneliner:     'A masterclass in tension and release — hold that bend until it hurts.',
    technique_tags:     ['pre-bend', 'vibrato', 'space'],
    user_annotations:   [],
    date_saved:         '2026-03-25',
  },
]

export const MOCK_SKILL_NODES: SkillNode[] = [
  { id: 'pitch_accuracy',  label: 'Pitch',    score: 0.75, sessions_count: 2, last_session_date: '2026-03-27', easiness_factor: 2.5, interval_days: 1, next_review_date: '2026-03-28' },
  { id: 'bend_accuracy',   label: 'Bending',  score: 0.55, sessions_count: 2, last_session_date: '2026-03-27', easiness_factor: 2.1, interval_days: 1, next_review_date: '2026-03-28' },
  { id: 'phrasing',        label: 'Phrasing', score: 0.60, sessions_count: 2, last_session_date: '2026-03-27', easiness_factor: 2.3, interval_days: 2, next_review_date: '2026-03-29' },
  { id: 'timing',          label: 'Timing',   score: 0.70, sessions_count: 1, last_session_date: '2026-03-24', easiness_factor: 2.5, interval_days: 4, next_review_date: '2026-03-31' },
  { id: 'dynamics',        label: 'Dynamics', score: 0.45, sessions_count: 0, last_session_date: '',           easiness_factor: 2.5, interval_days: 1, next_review_date: '2026-03-28' },
]
```

---

```src/stores/useAppStore.ts
import { create } from 'zustand'
import type { LessonJSON, Session, Lick, SkillNode, JamSnapshot, UserPrefs } from '@/src/types'
import {
  MOCK_USER,
  MOCK_LESSONS,
  MOCK_SESSIONS,
  MOCK_LICKS,
  MOCK_SKILL_NODES,
} from '@/utils/mockData'

interface CurrentSession {
  lessonId:     string
  sectionIndex: number
  step:         1 | 2 | 3 | 4 | 5
  isPlaying:    boolean
  speed:        number         // 0.5–1.0
  /** 0–1 playhead for loop / waveform UI (Slow step); reset snaps to loop start. */
  playbackProgress: number
}

interface AppState {
  user:         UserPrefs
  lessons:      LessonJSON[]
  sessions:     Session[]
  licks:        Lick[]
  skillNodes:   SkillNode[]
  jamSnapshots: JamSnapshot[]
  currentSession: CurrentSession | null

  // User actions
  updateUser:        (updates: Partial<UserPrefs>) => void
  completeOnboarding:() => void

  // Session actions
  startSession:    (lessonId: string, sectionIndex?: number) => void
  setSessionStep:  (step: 1 | 2 | 3 | 4 | 5) => void
  setSessionSpeed: (speed: number) => void
  togglePlay:      () => void
  /** Slow step: jump playhead to start of highlighted loop (pause; wire to expo-av seek later). */
  seekLoopStart:   () => void
  endSession:      () => void

  // Library actions
  saveSession:  (session: Session) => void
  saveLick:     (lick: Lick) => void
  saveLesson:   (lesson: LessonJSON) => void

  // Skill actions
  updateSkillNode: (id: string, updates: Partial<SkillNode>) => void
}

export const useAppStore = create<AppState>((set) => ({
  user:           MOCK_USER,
  lessons:        MOCK_LESSONS,
  sessions:       MOCK_SESSIONS,
  licks:          MOCK_LICKS,
  skillNodes:     MOCK_SKILL_NODES,
  jamSnapshots:   [],
  currentSession: null,

  updateUser: (updates) =>
    set((s) => ({ user: { ...s.user, ...updates } })),

  completeOnboarding: () =>
    set((s) => ({ user: { ...s.user, onboarded: true } })),

  startSession: (lessonId, sectionIndex = 0) =>
    set({
      currentSession: {
        lessonId,
        sectionIndex,
        step: 1,
        isPlaying: false,
        speed: 1,
        playbackProgress: 0.3,
      },
    }),

  setSessionStep: (step) =>
    set((s) => ({
      currentSession: s.currentSession ? { ...s.currentSession, step } : null,
    })),

  setSessionSpeed: (speed) =>
    set((s) => ({
      currentSession: s.currentSession ? { ...s.currentSession, speed } : null,
    })),

  togglePlay: () =>
    set((s) => ({
      currentSession: s.currentSession
        ? { ...s.currentSession, isPlaying: !s.currentSession.isPlaying }
        : null,
    })),

  seekLoopStart: () =>
    set((s) => ({
      currentSession: s.currentSession
        ? { ...s.currentSession, playbackProgress: 0.3, isPlaying: false }
        : null,
    })),

  endSession: () => set({ currentSession: null }),

  saveSession:  (session)  => set((s) => ({ sessions:   [session,  ...s.sessions]  })),
  saveLick:     (lick)     => set((s) => ({ licks:      [lick,     ...s.licks]     })),
  saveLesson:   (lesson)   => set((s) => ({ lessons:    [lesson,   ...s.lessons]   })),

  updateSkillNode: (id, updates) =>
    set((s) => ({
      skillNodes: s.skillNodes.map((n) => (n.id === id ? { ...n, ...updates } : n)),
    })),
}))
```

---

## Components

```components/WoodGradient.tsx
import { LinearGradient } from 'expo-linear-gradient'
import type { LinearGradientProps } from 'expo-linear-gradient'

interface WoodGradientProps extends Omit<LinearGradientProps, 'colors'> {
  variant?: 'background' | 'card'
}

const GRADIENTS = {
  background: ['#3D2317', '#2C1810'] as const,
  card:       ['#4A3728', '#3D2B1F'] as const,
}

export function WoodGradient({ variant = 'background', style, ...props }: WoodGradientProps) {
  return (
    <LinearGradient
      colors={GRADIENTS[variant]}
      start={{ x: 0, y: 0 }}
      end={variant === 'card' ? { x: 1, y: 1 } : { x: 0, y: 1 }}
      style={[{ flex: 1 }, style]}
      {...props}
    />
  )
}
```

```components/NoiseOverlay.native.tsx
// Stub until assets/images/noise.png is added (commit 0.5).
// Replace body with an <Image> at ~3% opacity repeating noise.png.
export function NoiseOverlay() {
  return null
}
```

```components/NoiseOverlay.web.tsx
export function NoiseOverlay() {
  return (
    <div
      style={{
        position:        'fixed',
        inset:           0,
        pointerEvents:   'none',
        zIndex:          50,
        opacity:         0.03,
        mixBlendMode:    'overlay',
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
      }}
    />
  )
}
```

```components/CoachNote.tsx
import { View, Text } from 'react-native'
import { MessageSquare } from 'lucide-react-native'
import colors from '@/src/constants/colors'

interface CoachNoteProps {
  text:       string
  className?: string
}

export function CoachNote({ text, className = '' }: CoachNoteProps) {
  return (
    <View className={`bg-wood-700/80 border border-wood-600/50 rounded-xl p-5 overflow-hidden relative ${className}`}>
      {/* Amber accent strip */}
      <View className="absolute left-0 top-0 bottom-0 w-1 bg-amber-accent/40" />

      <View className="flex-row gap-4 items-start">
        <View className="mt-1 w-8 h-8 rounded-full bg-wood-800 items-center justify-center border border-wood-600">
          <MessageSquare color={colors.amber.accent} size={16} strokeWidth={1.5} />
        </View>
        <Text className="flex-1 text-cream/90 text-[15px] leading-relaxed font-sans">
          {text}
        </Text>
      </View>
    </View>
  )
}
```

```components/SessionStepper.tsx
import { View, Text } from 'react-native'

const STEPS = ['Listen', 'Study', 'Slow', 'Play', 'Review']

interface SessionStepperProps {
  currentStep: number // 1–5
}

export function SessionStepper({ currentStep }: SessionStepperProps) {
  const trackPercent = ((currentStep - 1) / (STEPS.length - 1)) * 100

  return (
    <View className="w-full py-3 px-2">
      <View className="flex-row justify-between items-center relative">
        {/* Background track */}
        <View className="absolute left-0 right-0 top-[11px] h-[2px] bg-wood-700" />

        {/* Active track */}
        <View
          className="absolute top-[11px] h-[2px] bg-amber-accent"
          style={{ width: `${trackPercent}%` }}
        />

        {STEPS.map((step, index) => {
          const stepNum  = index + 1
          const isActive = stepNum === currentStep
          const isPast   = stepNum < currentStep

          return (
            <View key={step} className="items-center z-10">
              <View
                className={`w-6 h-6 rounded-full items-center justify-center ${
                  isActive
                    ? 'bg-amber-accent'
                    : isPast
                    ? 'bg-wood-600 border border-amber-accent/30'
                    : 'bg-wood-800 border border-wood-600'
                }`}
              >
                <Text
                  className={`text-[10px] font-sans-medium ${
                    isActive ? 'text-wood-900' : isPast ? 'text-amber-light/50' : 'text-muted-brown'
                  }`}
                >
                  {stepNum}
                </Text>
              </View>
              <Text
                className={`text-[9px] uppercase tracking-wider font-sans-medium mt-1 ${
                  isActive ? 'text-amber-light' : isPast ? 'text-cream/60' : 'text-muted-brown/50'
                }`}
              >
                {step}
              </Text>
            </View>
          )
        })}
      </View>
    </View>
  )
}
```

```components/WaveformVisualizer.tsx
import { View } from 'react-native'
import { useMemo } from 'react'

interface WaveformVisualizerProps {
  isPlaying:       boolean
  progress?:       number            // 0–1
  highlightRegion?:[number, number]  // [start, end] as 0–1 fractions
}

export function WaveformVisualizer({
  progress = 0,
  highlightRegion,
}: WaveformVisualizerProps) {
  const bars = useMemo(
    () =>
      Array.from({ length: 60 }).map((_, i) => {
        const sin = Math.sin(i * 0.2) * 0.5 + 0.5
        const cos = Math.cos(i * 0.5) * 0.5 + 0.5
        return Math.max(0.1, sin * 0.6 + cos * 0.4)
      }),
    [],
  )

  return (
    <View className="w-full h-24 flex-row items-end overflow-hidden rounded-lg bg-wood-800/50 border border-wood-700/50 p-2 relative">
      {/* Progress overlay */}
      <View
        className="absolute left-2 top-2 bottom-2 bg-amber-accent/10 border-r border-amber-accent/50 z-10"
        style={{ width: `${progress * 100}%` }}
        pointerEvents="none"
      />

      {/* Loop highlight */}
      {highlightRegion && (
        <View
          className="absolute top-2 bottom-2 bg-amber-light/10 border-l border-r border-amber-light/30"
          style={{
            left:  `${highlightRegion[0] * 100}%`,
            width: `${(highlightRegion[1] - highlightRegion[0]) * 100}%`,
          }}
          pointerEvents="none"
        />
      )}

      {bars.map((height, i) => {
        const isPast = i / bars.length <= progress
        return (
          <View
            key={i}
            className={`flex-1 rounded-t-sm mx-[0.5px] ${isPast ? 'bg-amber-accent' : 'bg-wood-600'}`}
            style={{ height: `${height * 100}%`, minHeight: 4, opacity: isPast ? 1 : 0.5 }}
          />
        )
      })}
    </View>
  )
}
```

```components/StemMixer.tsx
import { View, Text, Pressable } from 'react-native'
import { useState } from 'react'
import { Guitar, Music2, Drum, Mic } from 'lucide-react-native'
import colors from '@/src/constants/colors'

type StemKey = 'guitar' | 'bass' | 'drums' | 'vocals'

interface StemMixerProps {
  onMuteChange?: (active: Record<StemKey, boolean>) => void
  defaults?: Partial<Record<StemKey, boolean>>
}

const STEMS: { key: StemKey; label: string; Icon: typeof Guitar }[] = [
  { key: 'guitar', label: 'Guitar', Icon: Guitar },
  { key: 'bass',   label: 'Bass',   Icon: Music2  },
  { key: 'drums',  label: 'Drums',  Icon: Drum    },
  { key: 'vocals', label: 'Vocals', Icon: Mic     },
]

export function StemMixer({ onMuteChange, defaults }: StemMixerProps) {
  const [active, setActive] = useState<Record<StemKey, boolean>>({
    guitar: true,
    bass:   false,
    drums:  false,
    vocals: false,
    ...defaults,
  })

  const toggle = (key: StemKey) => {
    const next = { ...active, [key]: !active[key] }
    setActive(next)
    onMuteChange?.(next)
  }

  return (
    <View className="bg-wood-800/60 rounded-xl p-4 border border-wood-700/50">
      <Text className="text-xs uppercase tracking-wider text-muted-brown mb-3 font-sans-medium">
        Stem Mixer
      </Text>
      <View className="flex-row gap-2">
        {STEMS.map(({ key, label, Icon }) => {
          const isActive = active[key]
          return (
            <Pressable
              key={key}
              onPress={() => toggle(key)}
              className={`flex-1 items-center py-3 rounded-lg border ${
                isActive
                  ? 'bg-wood-700 border-amber-accent/40'
                  : 'bg-wood-900/50 border-transparent'
              }`}
            >
              <Icon
                color={isActive ? colors.amber.light : colors.muted.brown}
                size={20}
                strokeWidth={2}
              />
              <Text
                className={`text-[10px] font-sans-medium mt-1.5 ${
                  isActive ? 'text-amber-light' : 'text-muted-brown'
                }`}
              >
                {label}
              </Text>
            </Pressable>
          )
        })}
      </View>
    </View>
  )
}
```

```components/PitchIndicator.tsx
import { View, Text } from 'react-native'
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from 'react-native-reanimated'
import { useEffect, useState } from 'react'

interface PitchIndicatorProps {
  note:     string
  cents:    number   // -50 to +50
  isActive: boolean
}

export function PitchIndicator({ note, cents, isActive }: PitchIndicatorProps) {
  const [barWidth, setBarWidth]  = useState(0)
  const dotOffset = useSharedValue(0)

  useEffect(() => {
    if (barWidth > 0) {
      const clamped = Math.max(-50, Math.min(50, cents))
      // Map [-50, 50] → [0, barWidth], then center the 12px dot
      dotOffset.value = withSpring(
        ((clamped + 50) / 100) * barWidth - 6,
        { stiffness: 300, damping: 20 },
      )
    }
  }, [cents, barWidth])

  const dotStyle = useAnimatedStyle(() => ({
    left: dotOffset.value,
  }))

  const isPerfect = Math.abs(cents) < 5

  if (!isActive) {
    return (
      <View className="h-32 bg-wood-800/40 rounded-2xl border border-wood-700/50 items-center justify-center">
        <Text className="text-muted-brown text-sm font-sans">Waiting for guitar...</Text>
      </View>
    )
  }

  return (
    <View className="h-32 bg-wood-800/60 rounded-2xl border border-wood-700/50 items-center justify-center overflow-hidden px-6">
      <Text className="text-4xl font-serif text-cream mb-4">{note}</Text>

      {/* Tuning bar */}
      <View
        className="w-full h-1.5 bg-wood-900 rounded-full relative"
        onLayout={(e) => setBarWidth(e.nativeEvent.layout.width)}
      >
        {/* Centre tick */}
        <View
          className="absolute bg-wood-500"
          style={{ left: barWidth / 2 - 0.5, top: -4, width: 1, height: 10 }}
        />

        <Animated.View
          style={[
            dotStyle,
            {
              position:        'absolute',
              top:             -4,
              width:           12,
              height:          12,
              borderRadius:    6,
              backgroundColor: isPerfect ? '#7A9B6D' : '#D4A574',
            },
          ]}
        />
      </View>

      <View className="flex-row justify-between w-full mt-2">
        <Text className="text-[10px] text-muted-brown uppercase tracking-wider font-sans">Flat</Text>
        <Text className={`text-[10px] uppercase tracking-wider font-sans ${isPerfect ? 'text-success' : 'text-muted-brown'}`}>
          In Tune
        </Text>
        <Text className="text-[10px] text-muted-brown uppercase tracking-wider font-sans">Sharp</Text>
      </View>
    </View>
  )
}
```

```components/LickCard.tsx
import { View, Text, Pressable } from 'react-native'
import { Play, Tag } from 'lucide-react-native'
import type { Lick } from '@/src/types'
import colors from '@/src/constants/colors'

interface LickCardProps {
  lick:      Lick
  onPlay?:   () => void
  onDrill?:  () => void
}

export function LickCard({ lick, onPlay, onDrill }: LickCardProps) {
  return (
    <View className="bg-wood-700/80 border border-wood-600/50 rounded-xl p-5 overflow-hidden">
      <View className="flex-row justify-between items-start mb-3">
        <View className="flex-1 mr-3">
          <Text className="font-serif text-lg text-cream mb-0.5">{lick.song_title}</Text>
          <Text className="text-sm text-muted-brown font-sans">{lick.artist}</Text>
        </View>
        <Pressable
          onPress={onPlay}
          className="w-10 h-10 rounded-full bg-wood-800 items-center justify-center border border-wood-600"
        >
          <Play color={colors.amber.accent} size={16} fill={colors.amber.accent} style={{ marginLeft: 2 }} />
        </Pressable>
      </View>

      <View className="flex-row flex-wrap gap-2 mb-3">
        <View className="px-2 py-1 rounded bg-wood-800 border border-wood-700">
          <Text className="text-xs text-amber-light/80 font-sans">{lick.key}</Text>
        </View>
        <View className="px-2 py-1 rounded bg-wood-800 border border-wood-700">
          <Text className="text-xs text-cream/70 font-sans">{lick.position}</Text>
        </View>
      </View>

      <View className="flex-row flex-wrap gap-2 mb-3">
        {lick.technique_tags.map((tag) => (
          <View key={tag} className="flex-row items-center gap-1">
            <Tag color={colors.muted.brown} size={10} />
            <Text className="text-[10px] uppercase tracking-wider text-muted-brown font-sans">
              {tag}
            </Text>
          </View>
        ))}
      </View>

      <View className="pt-3 border-t border-wood-700/50">
        <Text className="text-sm text-cream/80 italic leading-relaxed font-sans">
          "{lick.coach_oneliner}"
        </Text>
      </View>

      <Pressable
        onPress={onDrill}
        className="mt-3 bg-wood-700 border border-wood-600 rounded-lg py-2 items-center"
      >
        <Text className="text-xs text-amber-light font-sans-medium uppercase tracking-wider">
          Drill this
        </Text>
      </Pressable>
    </View>
  )
}
```

```components/SkillGraph.tsx
// Radar chart using react-native-svg (no recharts dependency).
import { View } from 'react-native'
import Svg, { Polygon, Line, Circle, Text as SvgText, G } from 'react-native-svg'
import type { SkillNode } from '@/src/types'

interface SkillGraphProps {
  nodes: SkillNode[]
  size?: number
}

export function SkillGraph({ nodes, size = 280 }: SkillGraphProps) {
  const center = size / 2
  const radius = 90
  const levels = 5
  const total  = nodes.length

  const angleOf = (i: number) => (i * 2 * Math.PI) / total - Math.PI / 2
  const ptAt = (angle: number, r: number) => ({
    x: center + r * Math.cos(angle),
    y: center + r * Math.sin(angle),
  })

  const gridPolygons = Array.from({ length: levels }, (_, lvl) => {
    const r = (radius / levels) * (lvl + 1)
    return nodes.map((_, i) => {
      const pt = ptAt(angleOf(i), r)
      return `${pt.x},${pt.y}`
    }).join(' ')
  })

  const dataPoints = nodes.map((n, i) => {
    const r  = n.score * radius
    const pt = ptAt(angleOf(i), r)
    return `${pt.x},${pt.y}`
  }).join(' ')

  return (
    <View className="w-full bg-wood-800/40 rounded-2xl border border-wood-700/50 p-4 items-center">
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Grid rings */}
        {gridPolygons.map((pts, i) => (
          <Polygon key={i} points={pts} fill="none" stroke="#4A3728" strokeWidth={1} />
        ))}

        {/* Axis lines + labels */}
        {nodes.map((node, i) => {
          const angle   = angleOf(i)
          const axisEnd = ptAt(angle, radius)
          const label   = ptAt(angle, radius + 22)
          return (
            <G key={node.id}>
              <Line x1={center} y1={center} x2={axisEnd.x} y2={axisEnd.y} stroke="#4A3728" strokeWidth={1} />
              <SvgText
                x={label.x}
                y={label.y + 4}
                fill="#8B7D6B"
                fontSize={11}
                textAnchor="middle"
                fontFamily="DMSans-Regular"
              >
                {node.label}
              </SvgText>
            </G>
          )
        })}

        {/* Data polygon */}
        <Polygon points={dataPoints} fill="#D4A574" fillOpacity={0.2} stroke="#D4A574" strokeWidth={2} />

        {/* Data dots */}
        {nodes.map((n, i) => {
          const pt = ptAt(angleOf(i), n.score * radius)
          return <Circle key={n.id} cx={pt.x} cy={pt.y} r={4} fill="#D4A574" />
        })}
      </Svg>
    </View>
  )
}
```

```components/TabView.tsx
// Stub component for AlphaTab integration (commits 21–22).
// Replace contents with AlphaTabWebView (native) or AlphaTabWeb (web).
import { View, Text, ScrollView } from 'react-native'

interface TabViewProps {
  isSkeleton?: boolean
  label?:      string
}

const FULL_TAB = `e|-------------------------------|
B|-------7---10b12--10~----------|
G|---7-9---7---------------------|
D|-9-----------------------------|`

const SKELETON_TAB = `e|-------------------------------|
B|-----------10b12---------------|
G|-------------------------------|
D|-9-----------------------------|`

export function TabView({ isSkeleton = false, label }: TabViewProps) {
  return (
    <View className="w-full bg-[#1E1E1E] rounded-xl border border-wood-600/50 p-4 overflow-hidden">
      <View className="flex-row justify-between items-center mb-3">
        {label && (
          <Text className="text-xs text-muted-brown font-sans uppercase tracking-wider">{label}</Text>
        )}
        <View className="bg-wood-800 px-2 py-1 rounded border border-wood-700">
          <Text className="text-[10px] text-muted-brown uppercase tracking-wider font-sans">
            {isSkeleton ? 'Skeleton' : 'Full Tab'}
          </Text>
        </View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <Text className="font-mono text-sm text-cream/90 leading-relaxed">
          {isSkeleton ? SKELETON_TAB : FULL_TAB}
        </Text>
      </ScrollView>
    </View>
  )
}
```

---

## App Entry & Layouts

```app/_layout.tsx
import 'react-native-gesture-handler'
import 'react-native-reanimated'
import '../global.css'

import { DMSans_400Regular, DMSans_500Medium } from '@expo-google-fonts/dm-sans'
import { JetBrainsMono_400Regular } from '@expo-google-fonts/jetbrains-mono'
import {
  PlayfairDisplay_400Regular,
  PlayfairDisplay_400Regular_Italic,
  PlayfairDisplay_700Bold,
} from '@expo-google-fonts/playfair-display'
import { useFonts } from 'expo-font'
import { Stack } from 'expo-router'
import * as SplashScreen from 'expo-splash-screen'
import { useEffect } from 'react'
import { View } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'

import { NoiseOverlay } from '@/components/NoiseOverlay'

SplashScreen.preventAutoHideAsync()

export default function RootLayout() {
  const [loaded, error] = useFonts({
    'PlayfairDisplay-Regular': PlayfairDisplay_400Regular,
    'PlayfairDisplay-Bold': PlayfairDisplay_700Bold,
    'PlayfairDisplay-Italic': PlayfairDisplay_400Regular_Italic,
    'DMSans-Regular': DMSans_400Regular,
    'DMSans-Medium': DMSans_500Medium,
    'JetBrainsMono-Regular': JetBrainsMono_400Regular,
  })

  useEffect(() => {
    if (error) throw error
  }, [error])

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync()
  }, [loaded])

  if (!loaded) return null

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <View className="flex-1 bg-wood-900">
          <NoiseOverlay />
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="(tabs)" />
          </Stack>
        </View>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
```

```app/(tabs)/_layout.tsx
import { Tabs } from 'expo-router'
import { Home, Library, Activity, Settings } from 'lucide-react-native'
import colors from '@/src/constants/colors'

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown:            false,
        tabBarStyle: {
          backgroundColor: colors.wood[800],
          borderTopColor:  colors.wood[700] + '80',
          paddingBottom:   8,
          height:          64,
        },
        tabBarActiveTintColor:   colors.amber.light,
        tabBarInactiveTintColor: colors.muted.brown,
        tabBarLabelStyle: {
          fontFamily:    'DMSans-Medium',
          fontSize:      10,
          letterSpacing: 0.5,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => <Home color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="library"
        options={{
          title: 'Library',
          tabBarIcon: ({ color, size }) => <Library color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="progress"
        options={{
          title: 'Progress',
          tabBarIcon: ({ color, size }) => <Activity color={color} size={size} strokeWidth={2} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color, size }) => <Settings color={color} size={size} strokeWidth={2} />,
        }}
      />
    </Tabs>
  )
}
```

---

## Screens

### Play session

- **Layout:** In `app/session/play.tsx`: top row on wide screens is **~⅓ / ~⅔** — left column stacks **Pitch targets** then **Score · by beat**; right column is **Live pitch vs target** (+ streak line). Below that, **Position map** (`FretboardDiagram`) is **full width**. On narrow screens the column stacks (targets → score → ladder). The stem/tab block remains **`SessionStemAndTab`** below so the AlphaTab surface does not remount unnecessarily.
- **Panel tokens (align with `SessionStepScreen` / Listen):** `rounded-xl border border-wood-600/40 bg-cream-dark/50` for cards; section titles `font-sans-medium text-xs uppercase tracking-wide text-amber-accent`; body `text-wood-900` / secondary `text-muted-brown` — **not** separate dark-wood “dashboard” panels so Play reads as the same session chrome as Listen/Study.
- **B2 (targets):** The highlighted chip is always the **latest tab note** (`noteEvent`); the queue shows history so testers see targets advancing **note-by-note**, while beat scoring stays **per beat** against whatever target was in effect.
- **Chips:** Reuse the ListenStemPanel inactive/active chip pattern (`border-wood-600/40 bg-wood-900/10` vs `border-amber-accent bg-amber-accent`) for the horizontal target strip.
- **Motion:** `react-native-reanimated` only (see `PRIORITIES.md` — no `framer-motion`). Beat-close feedback on the fretboard uses a brief ring tint (success / amber / danger).
- **QA cross-links:** Manual checks in `docs/FEEL_REAL_QA.md` (B2 rolling targets, E1 ladder); platform matrix in `docs/PLATFORM_QA_MATRIX.md`.

```app/(tabs)/index.tsx
import { ScrollView, View, Text, Pressable } from 'react-native'
import { useRouter } from 'expo-router'
import { Play, Plus, Library, Clock } from 'lucide-react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { WoodGradient } from '@/components/WoodGradient'
import { CoachNote }    from '@/components/CoachNote'
import { useAppStore }  from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'

/** `Session.date` is ISO `YYYY-MM-DD`; format for list rows. */
function formatRelativeSessionDate(isoDate: string): string {
  const lastMs = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(isoDate) ? `${isoDate}T12:00:00` : isoDate)
  if (Number.isNaN(lastMs)) return isoDate
  const diffDays = Math.floor((Date.now() - lastMs) / 86400000)
  if (diffDays <= 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return new Date(lastMs).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function HomeScreen() {
  const router   = useRouter()
  const { user, lessons, sessions } = useAppStore()

  const recommendedLesson = lessons[0] ?? null
  const recentSessions    = sessions.slice(0, 2)

  const greeting = () => {
    if (!user.onboarded) return "First time here. Let's find out what you sound like."
    if (sessions.length === 0) return "You haven't practiced a specific song yet."
    const raw = sessions[0].date
    const lastMs = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(raw) ? `${raw}T12:00:00` : raw)
    if (Number.isNaN(lastMs)) {
      return "You've been working on your phrasing. There's one more thing worth trying."
    }
    const diffDays = Math.floor((Date.now() - lastMs) / 86400000)
    if (diffDays > 5) return "Been a few days. No pressure — let's just play something."
    return "You've been working on your phrasing. There's one more thing worth trying."
  }

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        <ScrollView className="flex-1 px-6" showsVerticalScrollIndicator={false}>
          {/* Header */}
          <View className="mt-8 mb-10">
            <Text className="text-3xl font-serif text-cream mb-1">Harmoniq</Text>
            <Text className="text-muted-brown font-sans leading-relaxed">{greeting()}</Text>
          </View>

          {/* Suggested session */}
          <Text className="text-xs uppercase tracking-wider text-muted-brown mb-4 font-sans-medium">
            Suggested Session
          </Text>

          {recommendedLesson ? (
            <View className="bg-wood-700/80 border border-wood-600/50 rounded-2xl p-6 mb-10 overflow-hidden">
              <View className="flex-row justify-between items-start mb-5">
                <View className="flex-1 mr-3">
                  <Text className="text-2xl font-serif text-cream mb-1">
                    {recommendedLesson.song_title}
                  </Text>
                  <Text className="text-amber-light/80 font-sans">{recommendedLesson.artist}</Text>
                </View>
                <View className="flex-row items-center gap-1 bg-wood-800/50 px-3 py-1.5 rounded-lg border border-wood-700">
                  <Clock color={colors.muted.brown} size={14} />
                  <Text className="text-muted-brown text-sm font-sans ml-1">~15 min</Text>
                </View>
              </View>

              <CoachNote
                text={recommendedLesson.sections[0]?.coach_note ?? ''}
                className="mb-5"
              />

              <Pressable
                onPress={() =>
                  router.push(`/session/listen?lessonId=${recommendedLesson.job_id}&section=0`)
                }
                className="bg-amber-accent rounded-xl py-3.5 flex-row items-center justify-center gap-2"
              >
                <Play color={colors.wood[900]} size={20} fill={colors.wood[900]} />
                <Text className="text-wood-900 font-sans-medium text-base">Start Session</Text>
              </Pressable>
            </View>
          ) : (
            <View className="bg-wood-800/40 border border-wood-700/50 rounded-2xl p-6 mb-10">
              <Text className="text-cream/80 font-sans leading-relaxed mb-4">
                You haven't practiced a specific song yet. Add one below and we'll build your first
                session around it.
              </Text>
              <Pressable
                onPress={() => router.push('/add-song')}
                className="bg-amber-accent rounded-xl py-3.5 items-center"
              >
                <Text className="text-wood-900 font-sans-medium">Add Song</Text>
              </Pressable>
            </View>
          )}

          {/* Quick actions */}
          <Text className="text-xs uppercase tracking-wider text-muted-brown mb-4 font-sans-medium">
            Quick Actions
          </Text>
          <View className="flex-row gap-3 mb-10">
            <Pressable
              onPress={() => router.push('/add-song')}
              className="flex-1 bg-wood-800/40 border border-wood-700/50 rounded-xl p-4 items-center gap-3"
              style={{ aspectRatio: 1 }}
            >
              <View className="w-10 h-10 rounded-full bg-wood-700 items-center justify-center">
                <Plus color={colors.amber.light} size={20} />
              </View>
              <Text className="text-sm text-cream font-sans-medium">Add Song</Text>
            </Pressable>
            <Pressable
              onPress={() => router.push('/library')}
              className="flex-1 bg-wood-800/40 border border-wood-700/50 rounded-xl p-4 items-center gap-3"
              style={{ aspectRatio: 1 }}
            >
              <View className="w-10 h-10 rounded-full bg-wood-700 items-center justify-center">
                <Library color={colors.amber.light} size={20} />
              </View>
              <Text className="text-sm text-cream font-sans-medium">Lick Library</Text>
            </Pressable>
          </View>

          {/* Recent sessions */}
          {recentSessions.length > 0 && (
            <>
              <Text className="text-xs uppercase tracking-wider text-muted-brown mb-4 font-sans-medium">
                Recent Sessions
              </Text>
              <View className="gap-3 mb-8">
                {recentSessions.map((session) => (
                  <View
                    key={session.id}
                    className="bg-wood-800/40 border border-wood-700/50 rounded-xl p-4 flex-row justify-between items-center"
                  >
                    <View>
                      <Text className="text-cream font-sans-medium mb-0.5">{session.song_title}</Text>
                      <Text className="text-xs text-muted-brown font-sans">{session.section_label}</Text>
                    </View>
                    <Text className="text-xs text-muted-brown font-sans">
                      {formatRelativeSessionDate(session.date)}
                    </Text>
                  </View>
                ))}
              </View>
            </>
          )}

          <View className="h-6" />
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```app/(tabs)/library.tsx
import { ScrollView, View, Text, TextInput, Pressable } from 'react-native'
import { useState } from 'react'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Search } from 'lucide-react-native'
import { WoodGradient } from '@/components/WoodGradient'
import { LickCard }     from '@/components/LickCard'
import { useAppStore }  from '@/src/stores/useAppStore'
import { useRouter }    from 'expo-router'
import colors from '@/src/constants/colors'

export default function LibraryScreen() {
  const router  = useRouter()
  const licks   = useAppStore((s) => s.licks)
  const [query, setQuery] = useState('')

  const filtered = licks.filter(
    (l) =>
      l.song_title.toLowerCase().includes(query.toLowerCase()) ||
      l.technique_tags.some((t) => t.toLowerCase().includes(query.toLowerCase())),
  )

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        <ScrollView className="flex-1 px-6" showsVerticalScrollIndicator={false}>
          <View className="mt-8 mb-6">
            <Text className="text-3xl font-serif text-cream mb-1">Lick Library</Text>
            <Text className="text-muted-brown font-sans">Your personal vocabulary of expressive phrases.</Text>
          </View>

          {/* Search bar */}
          <View className="flex-row items-center bg-wood-800/60 border border-wood-700 rounded-xl px-3 py-3 mb-6 gap-2">
            <Search color={colors.muted.brown} size={18} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search by song, artist, or technique..."
              placeholderTextColor={colors.muted.brown}
              className="flex-1 text-cream font-sans text-sm"
            />
          </View>

          {/* Lick list */}
          <View className="gap-4 mb-8">
            {filtered.map((lick) => (
              <LickCard
                key={lick.id}
                lick={lick}
                onPlay={() => {/* wire expo-av */}}
                onDrill={() => router.push(`/session/study?lickId=${lick.id}`)}
              />
            ))}
          </View>

          {filtered.length === 0 && (
            <View className="items-center py-20">
              <Text className="text-muted-brown font-sans">No licks found.</Text>
            </View>
          )}
          <View className="h-6" />
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```app/(tabs)/progress.tsx
import { ScrollView, View, Text, Pressable } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { WoodGradient } from '@/components/WoodGradient'
import { SkillGraph }   from '@/components/SkillGraph'
import { CoachNote }    from '@/components/CoachNote'
import { useAppStore }  from '@/src/stores/useAppStore'

export default function ProgressScreen() {
  const { skillNodes, sessions } = useAppStore()

  const topCoach = sessions[0]?.coach_review ?? ''

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        <ScrollView className="flex-1 px-6" showsVerticalScrollIndicator={false}>
          <View className="mt-8 mb-6">
            <Text className="text-3xl font-serif text-cream mb-1">Your Progress</Text>
            <Text className="text-muted-brown font-sans">A slow-moving map of your musical feel.</Text>
          </View>

          {/* Skill graph */}
          <Text className="text-xs uppercase tracking-wider text-muted-brown mb-4 font-sans-medium">
            Skill Map
          </Text>
          <SkillGraph nodes={skillNodes} />

          {topCoach ? (
            <>
              <Text className="text-xs uppercase tracking-wider text-muted-brown mt-8 mb-4 font-sans-medium">
                Latest Coach Note
              </Text>
              <CoachNote text={topCoach} />
            </>
          ) : null}

          {/* Session journal */}
          <Text className="text-xs uppercase tracking-wider text-muted-brown mt-8 mb-4 font-sans-medium">
            Session History
          </Text>
          <View className="gap-4 mb-8">
            {sessions.map((session) => (
              <View
                key={session.id}
                className="bg-wood-800/40 border border-wood-700/50 rounded-xl p-5"
              >
                <View className="flex-row justify-between items-start mb-3">
                  <View>
                    <Text className="text-lg font-serif text-cream">{session.song_title}</Text>
                    <Text className="text-sm text-amber-light/80 font-sans">
                      {session.section_label}
                    </Text>
                  </View>
                  <View className="items-end">
                    <Text className="text-sm text-muted-brown font-sans">
                      {formatRelativeSessionDate(session.date)}
                    </Text>
                    {session.duration_min && (
                      <Text className="text-xs text-muted-brown font-sans">
                        {session.duration_min} min
                      </Text>
                    )}
                  </View>
                </View>
                <Text className="text-sm text-cream/80 leading-relaxed pt-3 border-t border-wood-700/50 font-sans italic">
                  "{session.coach_review}"
                </Text>
              </View>
            ))}
          </View>
          <View className="h-6" />
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```app/(tabs)/settings.tsx
import { ScrollView, View, Text, Pressable, Switch } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Guitar, Mic, Download, Trash2, Info } from 'lucide-react-native'
import { WoodGradient } from '@/components/WoodGradient'
import { useAppStore }  from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'

export default function SettingsScreen() {
  const { user, updateUser } = useAppStore()

  const SettingRow = ({
    label,
    children,
    isLast = false,
  }: {
    label: string
    children: React.ReactNode
    isLast?: boolean
  }) => (
    <View
      className={`px-4 py-4 flex-row items-center justify-between ${
        !isLast ? 'border-b border-wood-700/50' : ''
      }`}
    >
      <Text className="text-cream font-sans">{label}</Text>
      {children}
    </View>
  )

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        <ScrollView className="flex-1 px-6" showsVerticalScrollIndicator={false}>
          <View className="mt-8 mb-8">
            <Text className="text-3xl font-serif text-cream">Settings</Text>
          </View>

          {/* Guitar setup */}
          <View className="flex-row items-center gap-2 mb-3">
            <Guitar color={colors.amber.light} size={18} strokeWidth={2} />
            <Text className="text-xs uppercase tracking-wider text-amber-light font-sans-medium">
              Guitar Setup
            </Text>
          </View>
          <View className="bg-wood-800/40 border border-wood-700/50 rounded-xl overflow-hidden mb-8">
            <SettingRow label="Guitar Type">
              <View className="flex-row gap-2">
                {(['Electric', 'Acoustic'] as const).map((type) => (
                  <Pressable
                    key={type}
                    onPress={() => updateUser({ guitar_type: type })}
                    className={`px-3 py-1.5 rounded-lg border ${
                      user.guitar_type === type
                        ? 'bg-amber-accent/20 border-amber-accent/50'
                        : 'border-wood-600'
                    }`}
                  >
                    <Text
                      className={`text-sm font-sans ${
                        user.guitar_type === type ? 'text-amber-light' : 'text-muted-brown'
                      }`}
                    >
                      {type}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </SettingRow>
            <SettingRow label="Tuning" isLast>
              <Text className="text-muted-brown text-sm font-sans">{user.tuning}</Text>
            </SettingRow>
          </View>

          {/* Audio & Practice */}
          <View className="flex-row items-center gap-2 mb-3">
            <Mic color={colors.amber.light} size={18} strokeWidth={2} />
            <Text className="text-xs uppercase tracking-wider text-amber-light font-sans-medium">
              Audio & Practice
            </Text>
          </View>
          <View className="bg-wood-800/40 border border-wood-700/50 rounded-xl overflow-hidden mb-8">
            <SettingRow label="Metronome default">
              <Switch
                value={user.metronome_default}
                onValueChange={(v) => updateUser({ metronome_default: v })}
                trackColor={{ false: colors.wood[600], true: colors.amber.accent }}
                thumbColor={colors.cream}
              />
            </SettingRow>
            <SettingRow label="Prefer simpler tabs" isLast>
              <Switch
                value={user.prefer_simpler_tabs}
                onValueChange={(v) => updateUser({ prefer_simpler_tabs: v })}
                trackColor={{ false: colors.wood[600], true: colors.amber.accent }}
                thumbColor={colors.cream}
              />
            </SettingRow>
          </View>

          {/* Coach voice */}
          <View className="flex-row items-center gap-2 mb-3">
            <Info color={colors.amber.light} size={18} strokeWidth={2} />
            <Text className="text-xs uppercase tracking-wider text-amber-light font-sans-medium">
              Coach Voice
            </Text>
          </View>
          <View className="bg-wood-800/40 border border-wood-700/50 rounded-xl overflow-hidden mb-8">
            {(['Encouraging', 'Direct', 'Mixed'] as const).map((v, i, arr) => (
              <Pressable
                key={v}
                onPress={() => updateUser({ coach_voice: v })}
                className={`px-4 py-4 flex-row items-center justify-between ${
                  i !== arr.length - 1 ? 'border-b border-wood-700/50' : ''
                }`}
              >
                <Text className="text-cream font-sans">{v}</Text>
                <View
                  className={`w-4 h-4 rounded-full border ${
                    user.coach_voice === v
                      ? 'bg-amber-accent border-amber-accent'
                      : 'border-wood-500'
                  }`}
                />
              </Pressable>
            ))}
          </View>

          {/* Data */}
          <View className="bg-wood-800/40 border border-wood-700/50 rounded-xl overflow-hidden mb-8">
            <Pressable className="px-4 py-4 flex-row items-center gap-3 border-b border-wood-700/50">
              <Download color={colors.amber.accent} size={16} />
              <Text className="text-cream font-sans">Export Practice Journal</Text>
            </Pressable>
            <Pressable className="px-4 py-4 flex-row items-center gap-3">
              <Trash2 color={colors.danger} size={16} />
              <Text className="text-danger font-sans">Clear Local Data</Text>
            </Pressable>
          </View>

          <Text className="text-xs text-muted-brown font-sans leading-relaxed px-1 mb-8">
            All audio processing happens locally on your device. Harmoniq does not upload or store
            your microphone audio anywhere.
          </Text>
          <View className="h-6" />
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```app/onboarding/index.tsx
import { View, Text, Pressable, ScrollView } from 'react-native'
import { useState } from 'react'
import Animated, {
  FadeInDown,
  FadeOutUp,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated'
import { useRouter } from 'expo-router'
import { Mic, Music, ArrowRight, Check } from 'lucide-react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { WoodGradient }  from '@/components/WoodGradient'
import { SkillGraph }    from '@/components/SkillGraph'
import { useAppStore }   from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'

const TOTAL_STEPS = 6

export default function OnboardingScreen() {
  const [step, setStep]   = useState(1)
  const router            = useRouter()
  const { updateUser, completeOnboarding, skillNodes } = useAppStore()

  const next = () => setStep((s) => Math.min(TOTAL_STEPS, s + 1))
  const prev = () => setStep((s) => Math.max(1, s - 1))

  const finish = () => {
    completeOnboarding()
    router.replace('/')
  }

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <Animated.View
            key="step1"
            entering={FadeInDown.duration(300)}
            exiting={FadeOutUp.duration(200)}
            className="items-center max-w-sm w-full"
          >
            <View className="w-16 h-16 rounded-full bg-amber-accent/20 items-center justify-center border border-amber-accent/30 mb-8">
              <Music color={colors.amber.accent} size={32} />
            </View>
            <Text className="text-4xl font-serif text-cream mb-4 text-center">
              Welcome to Harmoniq
            </Text>
            <Text className="text-muted-brown text-lg mb-10 leading-relaxed text-center font-sans">
              Practice less. Sound more like yourself.
            </Text>
            <Pressable
              onPress={next}
              className="w-full bg-amber-accent rounded-xl py-4 flex-row items-center justify-center gap-2"
            >
              <Text className="text-wood-900 font-sans-medium text-base">Let's hear you play</Text>
              <ArrowRight color={colors.wood[900]} size={18} />
            </Pressable>
          </Animated.View>
        )

      case 2:
        return (
          <Animated.View
            key="step2"
            entering={FadeInDown.duration(300)}
            exiting={FadeOutUp.duration(200)}
            className="max-w-sm w-full"
          >
            <View className="w-12 h-12 rounded-full bg-wood-800 items-center justify-center border border-wood-600 mb-6">
              <Mic color={colors.amber.accent} size={24} />
            </View>
            <Text className="text-3xl font-serif text-cream mb-4">We need to listen</Text>
            <Text className="text-muted-brown mb-8 leading-relaxed font-sans">
              Harmoniq uses your microphone to hear your phrasing, timing, and pitch. Everything is
              processed locally. We never record or upload your audio.
            </Text>
            <Pressable
              onPress={next}
              className="w-full bg-wood-700 border border-wood-500 rounded-xl py-4 items-center mb-3"
            >
              <Text className="text-cream font-sans-medium">Allow Microphone</Text>
            </Pressable>
            <Text className="text-xs text-muted-brown text-center px-4 font-sans">
              If you deny permission, core practice features won't work.
            </Text>
          </Animated.View>
        )

      case 3:
        return (
          <Animated.View
            key="step3"
            entering={FadeInDown.duration(300)}
            exiting={FadeOutUp.duration(200)}
            className="max-w-sm w-full"
          >
            <Text className="text-3xl font-serif text-cream mb-2">Your Setup</Text>
            <Text className="text-muted-brown mb-8 font-sans">What are you playing today?</Text>

            <View className="bg-wood-800/50 p-4 rounded-xl border border-wood-700 mb-4">
              <Text className="text-xs text-muted-brown mb-3 uppercase tracking-wider font-sans">
                Guitar Type
              </Text>
              <View className="flex-row gap-2">
                {(['Electric', 'Acoustic'] as const).map((t) => (
                  <Pressable
                    key={t}
                    onPress={() => updateUser({ guitar_type: t })}
                    className="flex-1 py-3 rounded-lg bg-wood-700 border border-wood-600 items-center"
                  >
                    <Text className="text-cream font-sans">{t}</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <Pressable
              onPress={next}
              className="w-full bg-amber-accent rounded-xl py-4 items-center"
            >
              <Text className="text-wood-900 font-sans-medium">Continue</Text>
            </Pressable>
          </Animated.View>
        )

      case 4:
        return (
          <Animated.View
            key="step4"
            entering={FadeInDown.duration(300)}
            exiting={FadeOutUp.duration(200)}
            className="max-w-sm w-full"
          >
            <Text className="text-3xl font-serif text-cream mb-2">Your Style</Text>
            <Text className="text-muted-brown mb-8 font-sans">What kind of playing moves you?</Text>

            <View className="flex-row flex-wrap gap-2 mb-8">
              {['Blues/Soul', 'Rock/Indie', 'Jazz', 'Neo-Soul', 'Metal', 'Acoustic/Fingerpicking'].map(
                (style) => (
                  <Pressable
                    key={style}
                    onPress={() => {
                      updateUser({ style_focus: [style] })
                      next()
                    }}
                    className="py-3.5 px-4 rounded-xl bg-wood-800 border border-wood-700 flex-row items-center justify-between"
                    style={{ minWidth: '47%' }}
                  >
                    <Text className="text-cream text-sm font-sans">{style}</Text>
                    <ArrowRight color={colors.muted.brown} size={14} />
                  </Pressable>
                ),
              )}
            </View>
          </Animated.View>
        )

      case 5:
        return (
          <Animated.View
            key="step5"
            entering={FadeInDown.duration(300)}
            exiting={FadeOutUp.duration(200)}
            className="max-w-sm w-full items-center"
          >
            <Text className="text-3xl font-serif text-cream mb-2 text-center">
              Quick Placement
            </Text>
            <Text className="text-muted-brown mb-6 text-center font-sans">
              Play a simple A minor pentatonic phrase. Don't overthink it — just play with feel.
            </Text>

            <View className="w-full bg-[#1E1E1E] p-5 rounded-xl border border-wood-600 mb-8">
              <Text className="font-mono text-cream/90 text-sm leading-relaxed">
                {`e|-----------------|\nB|-------5-8b10~---|\nG|---5-7-----------|\nD|-7---------------|`}
              </Text>
            </View>

            <View className="w-16 h-16 rounded-full bg-wood-800 border-2 border-amber-accent items-center justify-center mb-8">
              <Mic color={colors.amber.accent} size={24} />
            </View>

            <Pressable
              onPress={next}
              className="w-full bg-wood-700 border border-wood-500 rounded-xl py-4 items-center"
            >
              <Text className="text-cream font-sans">Skip for now</Text>
            </Pressable>
          </Animated.View>
        )

      case 6:
        return (
          <Animated.View
            key="step6"
            entering={FadeInDown.duration(300)}
            exiting={FadeOutUp.duration(200)}
            className="max-w-sm w-full"
          >
            <View className="items-center mb-6">
              <View className="w-12 h-12 rounded-full bg-success/20 border border-success/50 items-center justify-center">
                <Check color={colors.success} size={24} />
              </View>
            </View>
            <Text className="text-3xl font-serif text-cream mb-2 text-center">Your Baseline</Text>
            <Text className="text-muted-brown mb-8 text-center font-sans">
              We've mapped your current feel. Progress moves slowly here.
            </Text>

            <SkillGraph nodes={skillNodes} />

            <Pressable
              onPress={finish}
              className="w-full bg-amber-accent rounded-xl py-4 items-center mt-8"
            >
              <Text className="text-wood-900 font-sans-medium text-base">Start Practicing</Text>
            </Pressable>
          </Animated.View>
        )
    }
  }

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        {/* Step dots */}
        <View className="flex-row justify-end items-center px-6 pt-4 pb-2 gap-1.5">
          {step > 1 && step < TOTAL_STEPS && (
            <Pressable onPress={prev} className="mr-auto">
              <Text className="text-muted-brown font-sans-medium text-sm">Back</Text>
            </Pressable>
          )}
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <View
              key={i}
              className={`h-1.5 rounded-full bg-amber-accent transition-all ${
                i + 1 === step ? 'w-6' : i + 1 < step ? 'opacity-50 w-2' : 'opacity-20 w-2'
              }`}
            />
          ))}
        </View>

        <ScrollView
          contentContainerStyle={{ flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }}
          keyboardShouldPersistTaps="handled"
        >
          {renderStep()}
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```app/session/_layout.tsx
import { Stack, usePathname, useRouter } from 'expo-router'
import { View, Pressable } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { X } from 'lucide-react-native'
import { SessionStepper } from '@/components/SessionStepper'
import colors from '@/src/constants/colors'

const STEP_PATHS = ['listen', 'study', 'slow', 'play', 'review']

export default function SessionLayout() {
  const pathname = usePathname()
  const router   = useRouter()

  const stepIndex = STEP_PATHS.findIndex((s) => pathname.includes(s))
  const currentStep = (stepIndex >= 0 ? stepIndex + 1 : 1) as 1 | 2 | 3 | 4 | 5

  return (
    <SafeAreaView className="flex-1 bg-wood-900">
      {/* Session header */}
      <View className="flex-row items-center px-4 py-2 border-b border-wood-700/50 bg-wood-800/80">
        <Pressable onPress={() => router.replace('/')} className="p-2 mr-2">
          <X color={colors.muted.brown} size={22} strokeWidth={2} />
        </Pressable>
        <View className="flex-1">
          <SessionStepper currentStep={currentStep} />
        </View>
        <View className="w-10" />
      </View>

      <Stack screenOptions={{ headerShown: false, animation: 'none' }} />
    </SafeAreaView>
  )
}
```

```app/session/listen.tsx
import { View, Text, Pressable, ScrollView } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { Play, Pause, ArrowRight } from 'lucide-react-native'
import { WaveformVisualizer } from '@/components/WaveformVisualizer'
import { CoachNote }          from '@/components/CoachNote'
import { StemMixer }          from '@/components/StemMixer'
import { useAppStore }        from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'

export default function ListenScreen() {
  const router  = useRouter()
  const { lessonId, section = '0' } = useLocalSearchParams<{ lessonId: string; section: string }>()

  const { lessons, currentSession, togglePlay, setSessionStep, startSession } = useAppStore()

  const lesson       = lessons.find((l) => l.job_id === lessonId)
  const sectionIndex = parseInt(section, 10)
  const sec          = lesson?.sections[sectionIndex]

  // Ensure session is started
  if (!currentSession && lesson) startSession(lesson.job_id, sectionIndex)

  const isPlaying = currentSession?.isPlaying ?? false

  if (!lesson || !sec) {
    return (
      <View className="flex-1 bg-wood-900 items-center justify-center">
        <Text className="text-muted-brown font-sans">No lesson loaded.</Text>
      </View>
    )
  }

  return (
    <ScrollView className="flex-1 bg-wood-900 px-5" showsVerticalScrollIndicator={false}>
      {/* Song info */}
      <View className="items-center mt-8 mb-6">
        <Text className="text-2xl font-serif text-cream mb-1">{lesson.song_title}</Text>
        <Text className="text-muted-brown font-sans">
          {lesson.artist} · {lesson.key}
        </Text>
      </View>

      {/* Section chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} className="mb-5">
        <View className="flex-row gap-2 pr-4">
          {lesson.sections.map((s, i) => (
            <Pressable
              key={i}
              onPress={() =>
                router.push(`/session/listen?lessonId=${lessonId}&section=${i}`)
              }
              className={`px-3 py-1.5 rounded-full border ${
                i === sectionIndex
                  ? 'bg-amber-accent/20 border-amber-accent/50'
                  : 'border-wood-600 bg-wood-800/50'
              }`}
            >
              <Text
                className={`text-xs font-sans-medium ${
                  i === sectionIndex ? 'text-amber-light' : 'text-muted-brown'
                }`}
              >
                {s.label}
              </Text>
            </Pressable>
          ))}
        </View>
      </ScrollView>

      <WaveformVisualizer isPlaying={isPlaying} progress={0.0} className="mb-4" />

      {/* Transport */}
      <View className="flex-row justify-center gap-4 py-4 mb-4">
        <Pressable
          onPress={togglePlay}
          className="w-14 h-14 rounded-full bg-amber-accent items-center justify-center"
        >
          {isPlaying ? (
            <Pause color={colors.wood[900]} size={24} fill={colors.wood[900]} />
          ) : (
            <Play color={colors.wood[900]} size={24} fill={colors.wood[900]} style={{ marginLeft: 2 }} />
          )}
        </Pressable>
      </View>

      <CoachNote text={sec.coach_note} className="mb-4" />
      <StemMixer defaults={{ guitar: true, bass: false, drums: false, vocals: false }} className="mb-8" />

      <Pressable
        onPress={() => {
          setSessionStep(2)
          router.push(`/session/study?lessonId=${lessonId}&section=${section}`)
        }}
        className="w-full bg-wood-700 border border-wood-600 rounded-xl py-4 flex-row items-center justify-center gap-2 mb-10"
      >
        <Text className="text-cream font-sans">Next: Study</Text>
        <ArrowRight color={colors.cream} size={16} />
      </Pressable>
    </ScrollView>
  )
}
```

```app/session/study.tsx
import { View, Text, Pressable, ScrollView, TextInput } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { ArrowRight } from 'lucide-react-native'
import { TabView }  from '@/components/TabView'
import { CoachNote } from '@/components/CoachNote'
import { useAppStore } from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'
import { useState } from 'react'

export default function StudyScreen() {
  const router = useRouter()
  const { lessonId, section = '0' } = useLocalSearchParams<{ lessonId: string; section: string }>()
  const { lessons, user, setSessionStep } = useAppStore()
  const [isSkeleton, setIsSkeleton] = useState(true)
  const [note, setNote] = useState('')

  const lesson = lessons.find((l) => l.job_id === lessonId)
  const sec    = lesson?.sections[parseInt(section, 10)]

  if (!lesson || !sec) return null

  // Capo suggestion is a pure function based on key + position
  const capoSuggestion = (() => {
    if (lesson.key.includes('F#') || lesson.key.includes('Bb'))
      return 'Capo 2 keeps this in open G shapes — easier for position 1 fingering.'
    return null
  })()

  const isApproximate = sec.confidence < 0.7 || lesson.transcription_confidence < 0.6

  return (
    <ScrollView className="flex-1 bg-wood-900 px-5" showsVerticalScrollIndicator={false}>
      <View className="flex-row justify-between items-center mt-8 mb-4">
        <Text className="text-xl font-serif text-cream">Phrase Analysis</Text>
        <View className="bg-wood-800 px-2 py-1 rounded border border-wood-700">
          <Text className="text-xs text-amber-light font-sans">{sec.label} · {sec.primary_position}</Text>
        </View>
      </View>

      {/* Approximate tab warning */}
      {isApproximate && (
        <View className="bg-danger/10 border border-danger/30 rounded-xl px-4 py-3 mb-4">
          <Text className="text-danger text-sm font-sans leading-relaxed">
            This part is a rough approximation — use it as a guide, not a rule.
          </Text>
        </View>
      )}

      {/* Full / Skeleton toggle */}
      <View className="flex-row bg-wood-800 rounded-lg p-1 mb-4">
        {['Skeleton', 'Full'].map((label) => {
          const active = label === 'Skeleton' ? isSkeleton : !isSkeleton
          return (
            <Pressable
              key={label}
              onPress={() => setIsSkeleton(label === 'Skeleton')}
              className={`flex-1 py-2 rounded-md items-center ${active ? 'bg-wood-600' : ''}`}
            >
              <Text className={`text-xs font-sans-medium ${active ? 'text-cream' : 'text-muted-brown'}`}>
                {label}
              </Text>
            </Pressable>
          )
        })}
      </View>

      <TabView isSkeleton={isSkeleton} label={sec.label} />

      {/* Capo suggestion */}
      {capoSuggestion && (
        <View className="bg-amber-accent/10 border border-amber-accent/30 rounded-xl px-4 py-3 my-4">
          <Text className="text-amber-light/80 text-sm font-sans italic">{capoSuggestion}</Text>
        </View>
      )}

      <CoachNote text={sec.coach_explanation} className="my-4" />

      {/* Personal notes */}
      <View className="bg-wood-800/40 rounded-xl p-4 border border-wood-700/50 mb-4">
        <Text className="text-xs uppercase tracking-wider text-muted-brown mb-2 font-sans">
          Personal Notes
        </Text>
        <TextInput
          value={note}
          onChangeText={setNote}
          multiline
          placeholder="Add your own thoughts here..."
          placeholderTextColor={colors.muted.brown}
          className="text-cream font-sans text-sm leading-relaxed min-h-[80px]"
        />
      </View>

      <Pressable
        onPress={() => {
          setSessionStep(3)
          router.push(`/session/slow?lessonId=${lessonId}&section=${section}`)
        }}
        className="w-full bg-wood-700 border border-wood-600 rounded-xl py-4 flex-row items-center justify-center gap-2 mb-10"
      >
        <Text className="text-cream font-sans">Next: Slow & Loop</Text>
        <ArrowRight color={colors.cream} size={16} />
      </Pressable>
    </ScrollView>
  )
}
```

```app/session/slow.tsx
import { View, Text, Pressable } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { Play, Pause, RotateCcw, ArrowRight } from 'lucide-react-native'
import { WaveformVisualizer } from '@/components/WaveformVisualizer'
import { useAppStore }        from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'
import { useState } from 'react'

export default function SlowScreen() {
  const router  = useRouter()
  const { lessonId, section = '0' } = useLocalSearchParams<{ lessonId: string; section: string }>()
  const { currentSession, togglePlay, setSessionStep, setSessionSpeed, seekLoopStart } = useAppStore()

  const speed     = currentSession?.speed ?? 0.65
  const isPlaying = currentSession?.isPlaying ?? false
  const progress  = currentSession?.playbackProgress ?? 0.4

  return (
    <View className="flex-1 bg-wood-900 px-5">
      <Text className="text-xl font-serif text-cream text-center mt-8 mb-6">
        Isolate the hard part
      </Text>

      <WaveformVisualizer
        isPlaying={isPlaying}
        progress={progress}
        highlightRegion={[0.3, 0.5]}
      />

      {/* Transport */}
      <View className="flex-row justify-center gap-4 py-6">
        <Pressable
          onPress={seekLoopStart}
          accessibilityRole="button"
          accessibilityLabel="Reset loop to start"
          className="w-12 h-12 rounded-full bg-wood-800 border border-wood-600 items-center justify-center"
        >
          <RotateCcw color={colors.muted.brown} size={20} />
        </Pressable>
        <Pressable
          onPress={togglePlay}
          className="w-14 h-14 rounded-full bg-amber-accent items-center justify-center"
        >
          {isPlaying ? (
            <Pause color={colors.wood[900]} size={24} fill={colors.wood[900]} />
          ) : (
            <Play color={colors.wood[900]} size={24} fill={colors.wood[900]} style={{ marginLeft: 2 }} />
          )}
        </Pressable>
      </View>

      {/* Speed control */}
      <View className="bg-wood-800/60 rounded-xl p-5 border border-wood-700/50 mb-6">
        <View className="flex-row justify-between items-center mb-4">
          <Text className="text-sm text-muted-brown uppercase tracking-wider font-sans">Speed</Text>
          <Text className="text-amber-light font-mono">{Math.round(speed * 100)}%</Text>
        </View>

        {/* Speed buttons — native slider alternative until react-native-slider is wired */}
        <View className="flex-row gap-2 justify-center">
          {[50, 65, 75, 85, 100].map((pct) => (
            <Pressable
              key={pct}
              onPress={() => setSessionSpeed(pct / 100)}
              className={`flex-1 py-2.5 rounded-lg border items-center ${
                Math.round(speed * 100) === pct
                  ? 'bg-amber-accent border-amber-accent'
                  : 'border-wood-600 bg-wood-800'
              }`}
            >
              <Text
                className={`text-xs font-sans-medium ${
                  Math.round(speed * 100) === pct ? 'text-wood-900' : 'text-muted-brown'
                }`}
              >
                {pct}%
              </Text>
            </Pressable>
          ))}
        </View>

        <Text className="text-xs text-center text-muted-brown mt-3 font-sans">
          Pitch correction active
        </Text>
      </View>

      <Pressable
        onPress={() => {
          setSessionStep(4)
          router.push(`/session/play?lessonId=${lessonId}&section=${section}`)
        }}
        className="w-full bg-amber-accent rounded-xl py-4 flex-row items-center justify-center gap-2"
      >
        <Text className="text-wood-900 font-sans-medium text-base">Ready to Play</Text>
        <ArrowRight color={colors.wood[900]} size={18} />
      </Pressable>
    </View>
  )
}
```

```app/session/play.tsx
import { View, Text, Pressable } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useAppStore }     from '@/src/stores/useAppStore'
import { PitchIndicator }  from '@/components/PitchIndicator'
import { StemMixer }       from '@/components/StemMixer'
import colors from '@/src/constants/colors'

export default function PlayScreen() {
  const router  = useRouter()
  const { lessonId, section = '0' } = useLocalSearchParams<{ lessonId: string; section: string }>()
  const { setSessionStep } = useAppStore()

  // Wire usePitchStream hook here in commit 16 / 26
  const pitchNote  = 'B'
  const pitchCents = 12
  const isActive   = true

  return (
    <View className="flex-1 bg-wood-900 px-5 items-center justify-center gap-8">
      {/* Recording indicator */}
      <View className="flex-row items-center gap-2">
        <View className="w-2 h-2 rounded-full bg-amber-accent" />
        <Text className="text-sm text-amber-accent uppercase tracking-wider font-sans-medium">
          Listening
        </Text>
      </View>

      <View className="w-full max-w-sm">
        <PitchIndicator note={pitchNote} cents={pitchCents} isActive={isActive} />
      </View>

      <StemMixer
        defaults={{ guitar: false, bass: true, drums: true, vocals: false }}
        className="w-full max-w-sm"
      />

      <Text className="text-2xl font-serif text-cream text-center">Backing track playing</Text>
      <Text className="text-muted-brown font-sans text-center text-sm">
        Play along — tap Stop & Review when you're done
      </Text>

      <Pressable
        onPress={() => {
          setSessionStep(5)
          router.push(`/session/review?lessonId=${lessonId}&section=${section}`)
        }}
        className="w-full max-w-sm bg-wood-700 border border-wood-600 rounded-xl py-4 items-center"
      >
        <Text className="text-cream font-sans">Stop & Review</Text>
      </Pressable>
    </View>
  )
}
```

```app/session/review.tsx
import { View, Text, Pressable, ScrollView } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { Save, RotateCcw } from 'lucide-react-native'
import { CoachNote }   from '@/components/CoachNote'
import { WaveformVisualizer } from '@/components/WaveformVisualizer'
import { useAppStore } from '@/src/stores/useAppStore'
import colors from '@/src/constants/colors'

export default function ReviewScreen() {
  const router  = useRouter()
  const { lessonId, section = '0' } = useLocalSearchParams<{ lessonId: string; section: string }>()
  const { lessons, endSession, setSessionStep } = useAppStore()

  const lesson = lessons.find((l) => l.job_id === lessonId)
  const sec    = lesson?.sections[parseInt(section, 10)]

  // Placeholder: replace with real ScoreResult from POST /score in commit 27–28
  const mockReview =
    "You're rushing the end of the phrase. The pitch on the bend was great, but try holding that last note a full beat longer before releasing. Let it breathe."

  return (
    <ScrollView className="flex-1 bg-wood-900 px-5" showsVerticalScrollIndicator={false}>
      <Text className="text-2xl font-serif text-cream text-center mt-8 mb-6">Session Review</Text>

      <CoachNote text={mockReview} className="mb-6" />

      {/* Phrasing visualizer */}
      <View className="bg-wood-800/40 rounded-xl p-4 border border-wood-700/50 mb-6">
        <Text className="text-xs uppercase tracking-wider text-muted-brown mb-4 font-sans">
          Phrasing Comparison
        </Text>

        {/* Reference waveform */}
        <View className="gap-2">
          <View className="flex-row items-center gap-3">
            <Text className="text-[10px] text-muted-brown w-14 text-right font-sans">Original</Text>
            <View className="flex-1">
              <WaveformVisualizer isPlaying={false} progress={0.75} />
            </View>
          </View>
          <View className="flex-row items-center gap-3">
            <Text className="text-[10px] text-amber-light w-14 text-right font-sans">You</Text>
            <View className="flex-1">
              <WaveformVisualizer isPlaying={false} progress={0.52} />
            </View>
          </View>
        </View>

        <Text className="text-[10px] text-danger text-center mt-3 font-sans">
          Cut off early — hold those ending notes
        </Text>
      </View>

      {/* Actions */}
      <View className="flex-row gap-3 mb-4">
        <Pressable
          onPress={() => {/* commit 33: save to licks */}}
          className="flex-1 bg-wood-800 border border-wood-600 rounded-xl py-3 flex-row items-center justify-center gap-2"
        >
          <Save color={colors.amber.light} size={16} />
          <Text className="text-cream font-sans text-sm">Save Lick</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            setSessionStep(3)
            router.push(`/session/slow?lessonId=${lessonId}&section=${section}`)
          }}
          className="flex-1 bg-wood-800 border border-wood-600 rounded-xl py-3 flex-row items-center justify-center gap-2"
        >
          <RotateCcw color={colors.muted.brown} size={16} />
          <Text className="text-cream font-sans text-sm">Try Again</Text>
        </Pressable>
      </View>

      <Pressable
        onPress={() => {
          endSession()
          router.replace('/')
        }}
        className="w-full bg-amber-accent rounded-xl py-4 items-center mb-10"
      >
        <Text className="text-wood-900 font-sans-medium text-base">Finish Session</Text>
      </Pressable>
    </ScrollView>
  )
}
```

---

## Interaction Patterns

> These patterns close the gap between "functional" and Yousician-level polished. Apply them across every screen from Phase 2 onward. The single highest-leverage change is replacing every bare `Pressable` with `AnimatedPressable`.

### Rule: every touchable element must respond visually and haptically.

```components/AnimatedPressable.tsx
// Drop-in replacement for Pressable everywhere in the app.
// Gives every button a spring scale response + optional haptic.
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from 'react-native-reanimated'
import { Pressable, type PressableProps } from 'react-native'
import * as Haptics from 'expo-haptics'

type HapticStrength = 'light' | 'medium' | 'heavy' | 'none'

interface AnimatedPressableProps extends PressableProps {
  haptic?: HapticStrength
}

export function AnimatedPressable({
  onPress,
  haptic = 'light',
  style,
  children,
  ...props
}: AnimatedPressableProps) {
  const scale = useSharedValue(1)

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }))

  const handlePressIn = () => {
    scale.value = withSpring(0.97, { damping: 20, stiffness: 400 })
  }

  const handlePressOut = () => {
    scale.value = withSpring(1.0, { damping: 15, stiffness: 300 })
  }

  const handlePress: PressableProps['onPress'] = (e) => {
    if (haptic !== 'none') {
      const style = {
        light:  Haptics.ImpactFeedbackStyle.Light,
        medium: Haptics.ImpactFeedbackStyle.Medium,
        heavy:  Haptics.ImpactFeedbackStyle.Heavy,
      }[haptic]
      Haptics.impactAsync(style)
    }
    onPress?.(e)
  }

  return (
    <Animated.View style={[animStyle, style]}>
      <Pressable
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        onPress={handlePress}
        {...props}
      >
        {children}
      </Pressable>
    </Animated.View>
  )
}
```

```src/constants/animations.ts
// Shared animation presets. Pass directly to withSpring / withTiming.
export const spring = {
  gentle: { damping: 20, stiffness: 200 }, // page transitions, card reveals
  snappy: { damping: 20, stiffness: 400 }, // button press in
  bounce: { damping: 12, stiffness: 300 }, // success states
} as const

export const timing = {
  fast:   150,
  normal: 250,
  slow:   400,
} as const

// Stagger entrance animations: multiply by child index
export const entranceDelay = (index: number) => index * 60
```

### Skeleton loading state

Use during analysis polling, initial library load, and any async fetch screen.

```components/LoadingSkeleton.tsx
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'
import { useEffect } from 'react'
import type { ViewStyle } from 'react-native'

interface LoadingSkeletonProps {
  width?:        number | `${number}%`
  height?:       number
  borderRadius?: number
  style?:        ViewStyle
}

export function LoadingSkeleton({
  width        = '100%',
  height       = 16,
  borderRadius = 8,
  style,
}: LoadingSkeletonProps) {
  const opacity = useSharedValue(0.3)

  useEffect(() => {
    opacity.value = withRepeat(withTiming(0.75, { duration: 800 }), -1, true)
  }, [])

  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }))

  return (
    <Animated.View
      style={[{ width, height, borderRadius, backgroundColor: '#4A3728' }, animStyle, style]}
    />
  )
}
```

### Empty states

```components/EmptyState.tsx
import { View, Text } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import type { LucideIcon }   from 'lucide-react-native'
import colors from '@/src/constants/colors'

interface EmptyStateProps {
  Icon:       LucideIcon
  heading:    string
  subtext:    string
  ctaLabel?:  string
  onCta?:     () => void
}

export function EmptyState({ Icon, heading, subtext, ctaLabel, onCta }: EmptyStateProps) {
  return (
    <View className="flex-1 items-center justify-center px-10 gap-4">
      <View className="w-20 h-20 rounded-full bg-wood-800 border border-wood-700/50 items-center justify-center mb-2">
        <Icon color={colors.amber.accent} size={36} strokeWidth={1.5} />
      </View>
      <Text className="text-xl font-serif text-cream text-center">{heading}</Text>
      <Text className="text-muted-brown font-sans text-center leading-relaxed">{subtext}</Text>
      {ctaLabel && onCta && (
        <AnimatedPressable
          onPress={onCta}
          className="mt-4 bg-amber-accent rounded-xl px-8 py-3.5"
        >
          <Text className="text-wood-900 font-sans-medium">{ctaLabel}</Text>
        </AnimatedPressable>
      )}
    </View>
  )
}
```

### Inline error banner

```components/ErrorBanner.tsx
// Renders inline — not a modal. Use for confidence warnings, score failures,
// browser mic blocked, and any inline error in the README error table.
import { View, Text, Pressable } from 'react-native'
import { AlertTriangle, X }      from 'lucide-react-native'
import { useState }              from 'react'
import colors from '@/src/constants/colors'

type BannerVariant = 'warning' | 'error' | 'info'

interface ErrorBannerProps {
  message:      string
  variant?:     BannerVariant
  action?:      { label: string; onPress: () => void }
  dismissible?: boolean
  className?:   string
}

const STYLES: Record<BannerVariant, { bg: string; border: string; text: string; iconColor: string }> = {
  warning: { bg: 'bg-amber-accent/10', border: 'border-amber-accent/30', text: 'text-amber-light', iconColor: colors.amber.light  },
  error:   { bg: 'bg-danger/10',       border: 'border-danger/30',       text: 'text-danger',      iconColor: colors.danger       },
  info:    { bg: 'bg-wood-700/50',     border: 'border-wood-600/50',     text: 'text-cream/80',    iconColor: colors.muted.brown  },
}

export function ErrorBanner({
  message,
  variant     = 'warning',
  action,
  dismissible = true,
  className   = '',
}: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false)
  const s = STYLES[variant]
  if (dismissed) return null

  return (
    <View className={`${s.bg} border ${s.border} rounded-xl px-4 py-3 flex-row items-start gap-3 ${className}`}>
      <AlertTriangle color={s.iconColor} size={16} strokeWidth={2} style={{ marginTop: 2 }} />
      <Text className={`flex-1 ${s.text} text-sm font-sans leading-relaxed`}>{message}</Text>
      <View className="flex-row items-center gap-3">
        {action && (
          <Pressable onPress={action.onPress}>
            <Text className={`${s.text} text-sm font-sans-medium underline`}>{action.label}</Text>
          </Pressable>
        )}
        {dismissible && (
          <Pressable onPress={() => setDismissed(true)}>
            <X color={s.iconColor} size={14} />
          </Pressable>
        )}
      </View>
    </View>
  )
}
```

### Toast notifications

Install `react-native-toast-message`. Register at root once; call `toast.success()` / `toast.error()` from anywhere.

```components/ToastConfig.tsx
// Usage: import { toast } from '@/components/ToastConfig'
//        toast.success('Lick saved!')
// Wire:  add <Toast config={toastConfig} /> just before </View> in app/_layout.tsx
import Toast, { type BaseToastProps } from 'react-native-toast-message'
import { View, Text } from 'react-native'
import { Check, AlertTriangle } from 'lucide-react-native'
import colors from '@/src/constants/colors'

const WoodToast = ({
  text1,
  icon,
}: BaseToastProps & { icon: React.ReactNode }) => (
  <View className="mx-4 bg-wood-700 border border-wood-600/50 rounded-2xl px-4 py-3.5 flex-row items-center gap-3">
    {icon}
    <Text className="flex-1 text-cream font-sans text-sm">{text1}</Text>
  </View>
)

export const toastConfig = {
  success: (props: BaseToastProps) => (
    <WoodToast {...props} icon={<Check color={colors.success} size={18} />} />
  ),
  error: (props: BaseToastProps) => (
    <WoodToast {...props} icon={<AlertTriangle color={colors.danger} size={18} />} />
  ),
}

export const toast = {
  success: (text: string) =>
    Toast.show({ type: 'success', text1: text, visibilityTime: 2500, position: 'bottom' }),
  error: (text: string) =>
    Toast.show({ type: 'error', text1: text, visibilityTime: 3500, position: 'bottom' }),
}
```

---

## API Client

```src/api/analyze.ts
import type { AnalyzeJob, LessonJSON, ScoreResult } from '@/src/types'

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, body || res.statusText)
  }
  return res.json() as Promise<T>
}

// ── Analysis ───────────────────────────────────────────────────────

export async function submitAnalyzeJob(input: {
  youtube_url?: string
  file?: Blob
  filename?: string
}): Promise<string> {
  const form = new FormData()
  if (input.youtube_url) {
    form.append('youtube_url', input.youtube_url)
  } else if (input.file) {
    form.append('file', input.file, input.filename ?? 'upload.mp3')
  } else {
    throw new Error('Provide youtube_url or file')
  }
  const { job_id } = await request<{ job_id: string }>('/analyze', { method: 'POST', body: form })
  return job_id
}

export async function getJobStatus(jobId: string): Promise<AnalyzeJob> {
  return request<AnalyzeJob>(`/analyze/${jobId}`)
}

export function pollAnalyzeJob(
  jobId:      string,
  onStatus:   (job: AnalyzeJob) => void,
  intervalMs = 3000,
): Promise<LessonJSON> {
  return new Promise((resolve, reject) => {
    const id = setInterval(async () => {
      try {
        const job = await getJobStatus(jobId)
        onStatus(job)
        if (job.status === 'complete' && job.result) {
          clearInterval(id); resolve(job.result)
        } else if (job.status === 'failed') {
          clearInterval(id); reject(new ApiError(500, job.error ?? 'Analysis failed'))
        }
      } catch (e) { clearInterval(id); reject(e) }
    }, intervalMs)
  })
}

// ── Scoring ────────────────────────────────────────────────────────

export async function submitScore(payload: {
  recording_wav_base64: string
  section:              unknown
  skill_nodes:          string[]
}): Promise<ScoreResult> {
  return request<ScoreResult>('/score', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  })
}

export async function submitJamScore(payload: {
  recording_wav_base64: string
  duration_seconds:     number
}): Promise<{ coach_summary: string; scale_position_map: Record<string, number> }> {
  return request('/jam-score', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  })
}
```

---

## Missing Screens

```app/add-song.tsx
import { View, Text, TextInput, ActivityIndicator, ScrollView, Platform } from 'react-native'
import { useState } from 'react'
import { useRouter } from 'expo-router'
import { SafeAreaView } from 'react-native-safe-area-context'
import { X, Link, Check } from 'lucide-react-native'
import { WoodGradient }           from '@/components/WoodGradient'
import { AnimatedPressable }      from '@/components/AnimatedPressable'
import { ErrorBanner }            from '@/components/ErrorBanner'
import { LoadingSkeleton }        from '@/components/LoadingSkeleton'
import { useAppStore }            from '@/src/stores/useAppStore'
import { submitAnalyzeJob, pollAnalyzeJob } from '@/src/api/analyze'
import { toast }                  from '@/components/ToastConfig'
import colors from '@/src/constants/colors'
import type { AnalyzeJob } from '@/src/types'

type ScreenState = 'idle' | 'analyzing' | 'done' | 'error'

const STATUS_COPY: Record<AnalyzeJob['status'], string> = {
  processing: 'Separating stems and analyzing your track...',
  complete:   'Done!',
  failed:     'Something went wrong.',
}

export default function AddSongScreen() {
  const router = useRouter()
  const { saveLesson } = useAppStore()

  const [url,       setUrl]       = useState('')
  const [state,     setState]     = useState<ScreenState>('idle')
  const [jobStatus, setJobStatus] = useState<AnalyzeJob['status']>('processing')
  const [errorMsg,  setErrorMsg]  = useState('')

  const handleAnalyze = async () => {
    const trimmed = url.trim()
    if (!trimmed) return
    setState('analyzing')
    setErrorMsg('')
    try {
      const jobId  = await submitAnalyzeJob({ youtube_url: trimmed })
      const lesson = await pollAnalyzeJob(jobId, (j) => setJobStatus(j.status))
      saveLesson(lesson)
      setState('done')
      toast.success(`"${lesson.song_title}" is ready.`)
      setTimeout(() => router.replace('/'), 1000)
    } catch (e) {
      setErrorMsg(
        e instanceof Error
          ? e.message
          : 'Something went wrong processing that song. Try a studio recording.',
      )
      setState('error')
    }
  }

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        <View className="flex-row items-center px-5 pt-4 pb-3 border-b border-wood-700/50">
          <AnimatedPressable onPress={() => router.back()} className="p-2 mr-2" haptic="light">
            <X color={colors.muted.brown} size={22} />
          </AnimatedPressable>
          <Text className="text-lg font-serif text-cream">Add a Song</Text>
        </View>

        <ScrollView className="flex-1 px-5 pt-6" keyboardShouldPersistTaps="handled">
          {(state === 'idle' || state === 'error') && (
            <>
              <Text className="text-xs uppercase tracking-wider text-muted-brown mb-3 font-sans-medium">
                YouTube URL
              </Text>
              <View className="flex-row items-center bg-wood-800/60 border border-wood-700 rounded-xl px-4 py-3.5 gap-3 mb-4">
                <Link color={colors.muted.brown} size={18} />
                <TextInput
                  value={url}
                  onChangeText={setUrl}
                  placeholder="https://youtube.com/watch?v=..."
                  placeholderTextColor={colors.muted.brown}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                  returnKeyType="go"
                  onSubmitEditing={handleAnalyze}
                  className="flex-1 text-cream font-sans text-sm"
                />
              </View>

              {state === 'error' && (
                <ErrorBanner message={errorMsg} variant="error" className="mb-4" />
              )}

              <AnimatedPressable
                onPress={handleAnalyze}
                className="bg-amber-accent rounded-xl py-4 items-center mb-6"
                haptic="medium"
              >
                <Text className="text-wood-900 font-sans-medium text-base">Analyze Song</Text>
              </AnimatedPressable>

              {/* Web drag-drop rendered on web platform only */}
              {Platform.OS === 'web' && (
                <Text className="text-xs text-muted-brown font-sans text-center mb-6">
                  or drag & drop an MP3/WAV/M4A file above
                </Text>
              )}

              <Text className="text-xs text-muted-brown font-sans text-center px-4 leading-relaxed">
                Works best with studio recordings. Live versions sometimes have unusual audio.
              </Text>
            </>
          )}

          {state === 'analyzing' && (
            <View className="items-center pt-12 gap-6">
              <ActivityIndicator color={colors.amber.accent} size="large" />
              <Text className="text-cream font-serif text-2xl text-center">Listening to your track</Text>
              <Text className="text-muted-brown font-sans text-center">{STATUS_COPY[jobStatus]}</Text>
              <View className="w-full gap-3 mt-4">
                <LoadingSkeleton height={20} width="60%" style={{ alignSelf: 'center' }} />
                <LoadingSkeleton height={14} width="40%" style={{ alignSelf: 'center' }} />
                <LoadingSkeleton height={80} borderRadius={12} />
              </View>
            </View>
          )}

          {state === 'done' && (
            <View className="items-center pt-20 gap-4">
              <View className="w-16 h-16 rounded-full bg-success/20 border border-success/50 items-center justify-center">
                <Check color={colors.success} size={32} />
              </View>
              <Text className="text-2xl font-serif text-cream">Ready to play</Text>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```app/jam.tsx
import { View, Text, ScrollView } from 'react-native'
import { useState } from 'react'
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'
import { SafeAreaView } from 'react-native-safe-area-context'
import { WoodGradient }      from '@/components/WoodGradient'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner }       from '@/components/ErrorBanner'
import { useAppStore }       from '@/src/stores/useAppStore'
import { toast }             from '@/components/ToastConfig'
import colors from '@/src/constants/colors'

const TRACKS = [
  { id: 'am-blues',        label: 'A minor · Blues shuffle',  bpm: 70   },
  { id: 'am-drone',        label: 'A minor · Open drone',     bpm: null },
  { id: 'g-fingerpicking', label: 'G major · Fingerpicking',  bpm: 80   },
  { id: 'em-vamp',         label: 'E minor · Two-chord vamp', bpm: 90   },
  { id: 'g-ballad',        label: 'G major · Slow ballad',    bpm: 65   },
]

export default function JamScreen() {
  const [isJamming,     setIsJamming]     = useState(false)
  const [selectedTrack, setSelectedTrack] = useState(TRACKS[0].id)
  const [scaleLabel,    setScaleLabel]    = useState('—')
  const [webMicBlocked, setWebMicBlocked] = useState(false)

  const pulse = useSharedValue(1)
  const ringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
    opacity: 0.5 + (pulse.value - 1) * 3,
  }))

  const startJam = () => {
    setIsJamming(true)
    pulse.value = withRepeat(withTiming(1.12, { duration: 900 }), -1, true)
    // Wire: expo-av playback for selectedTrack (commit 36)
    // Wire: usePitchStream → pitchClassHistogram → setScaleLabel (commit 36)
  }

  const stopJam = () => {
    setIsJamming(false)
    pulse.value = withTiming(1)
    // Wire: stop audio, POST /jam-score, save JamSnapshot (commit 36)
    toast.success('Jam saved. Check Progress for a summary.')
  }

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1">
        <ScrollView
          className="flex-1 px-5"
          contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}
          showsVerticalScrollIndicator={false}
        >
          <View className="mt-8 mb-4">
            <Text className="text-3xl font-serif text-cream mb-1">Jam Mode</Text>
            <Text className="text-muted-brown font-sans">No task. No score. Just play.</Text>
          </View>

          {webMicBlocked && (
            <ErrorBanner
              message="Your browser is blocking mic access — click the lock icon to enable it."
              variant="error"
              action={{ label: 'Retry', onPress: () => setWebMicBlocked(false) }}
              className="mb-4"
            />
          )}

          {/* Track picker (hidden while jamming) */}
          {!isJamming && (
            <View className="gap-2 mb-6">
              <Text className="text-xs uppercase tracking-wider text-muted-brown mb-2 font-sans-medium">
                Backing Track
              </Text>
              {TRACKS.map((track) => (
                <AnimatedPressable
                  key={track.id}
                  onPress={() => setSelectedTrack(track.id)}
                  haptic="light"
                  className={`flex-row justify-between items-center p-4 rounded-xl border ${
                    selectedTrack === track.id
                      ? 'bg-amber-accent/10 border-amber-accent/40'
                      : 'bg-wood-800/40 border-wood-700/50'
                  }`}
                >
                  <Text
                    className={`font-sans text-sm ${
                      selectedTrack === track.id ? 'text-amber-light' : 'text-cream'
                    }`}
                  >
                    {track.label}
                  </Text>
                  {track.bpm ? (
                    <Text className="text-xs text-muted-brown font-mono">{track.bpm} BPM</Text>
                  ) : null}
                </AnimatedPressable>
              ))}
            </View>
          )}

          {/* Active jam: pulsing ring + scale label */}
          {isJamming && (
            <View className="flex-1 items-center justify-center gap-6">
              <Animated.View
                style={ringStyle}
                className="w-36 h-36 rounded-full border-2 border-amber-accent/60 items-center justify-center"
              >
                <View className="w-28 h-28 rounded-full bg-amber-accent/10 border border-amber-accent/30 items-center justify-center">
                  <Text className="text-amber-accent font-mono text-lg">{scaleLabel}</Text>
                </View>
              </Animated.View>
              <Text className="text-muted-brown font-sans text-sm">Listening...</Text>
            </View>
          )}

          {/* CTA */}
          <View className="pb-8 gap-3">
            {isJamming ? (
              <AnimatedPressable
                onPress={stopJam}
                haptic="medium"
                className="bg-wood-700 border border-wood-600 rounded-xl py-4 items-center"
              >
                <Text className="text-cream font-sans-medium">Stop & Save</Text>
              </AnimatedPressable>
            ) : (
              <AnimatedPressable
                onPress={startJam}
                haptic="medium"
                className="bg-amber-accent rounded-xl py-4 items-center"
              >
                <Text className="text-wood-900 font-sans-medium text-base">Start Jamming</Text>
              </AnimatedPressable>
            )}
          </View>
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
```

```components/AudioDropzone.web.tsx
// Web-only drag-and-drop upload zone. Conditionally rendered in add-song.tsx.
import { useState, useCallback } from 'react'

interface AudioDropzoneProps {
  onFile:   (file: File) => void
  accept?:  string
}

export function AudioDropzone({
  onFile,
  accept = '.mp3,.wav,.m4a,audio/*',
}: AudioDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) onFile(file)
    },
    [onFile],
  )

  const handleClick = () => {
    const input  = document.createElement('input')
    input.type   = 'file'
    input.accept = accept
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) onFile(file)
    }
    input.click()
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={handleClick}
      style={{
        border:        `2px dashed ${isDragging ? '#D4A574' : '#4A3728'}`,
        borderRadius:  12,
        padding:       32,
        textAlign:     'center',
        cursor:        'pointer',
        background:    isDragging ? 'rgba(212,165,116,0.06)' : 'rgba(61,35,23,0.4)',
        transition:    'all 0.2s ease',
        color:         isDragging ? '#E8B86D' : '#8B7D6B',
        fontFamily:    '"DM Sans", sans-serif',
        fontSize:      14,
      }}
    >
      {isDragging
        ? 'Drop to upload'
        : 'Drag an audio file here, or click to browse (MP3, WAV, M4A)'}
    </div>
  )
}
```

---

## AlphaTab Harness

```assets/alphatab-harness/index.html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { background: #2B1D0E; overflow-x: hidden; }
    #alphatab { width: 100%; min-height: 100vh; }
  </style>
</head>
<body>
  <div id="alphatab"></div>
  <!-- Pin version — never use @latest -->
  <script src="https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.3.1/dist/alphaTab.min.js"></script>
  <script>
    const api = new alphaTab.AlphaTabApi(document.getElementById('alphatab'), {
      display: {
        resources: {
          mainGlyphColor:      '#F0DEB4',
          secondaryGlyphColor: '#D4A574',
          barSeparatorColor:   '#5C4535',
          scoreInfoColor:      '#A08060',
          staffLineColor:      '#5C4535',
          barNumberColor:      '#8B7D6B',
        },
        scale: 1.1,
      },
      player: { enablePlayer: false },
    })

    // Inbound messages from React Native / parent frame
    window.addEventListener('message', (event) => {
      let msg
      try { msg = JSON.parse(typeof event.data === 'string' ? event.data : JSON.stringify(event.data)) }
      catch { return }

      if (msg.type === 'setScore' && msg.gp5Base64) {
        const bytes = Uint8Array.from(atob(msg.gp5Base64), (c) => c.charCodeAt(0))
        api.load(bytes.buffer)
      }
      if (msg.type === 'scrollToBar' && typeof msg.barIndex === 'number') {
        api.tickPosition = api.timePositionToTickPosition(msg.barIndex * 4000)
      }
    })

    // Outbound — post to both ReactNativeWebView (native) and window.parent (web iframe)
    const postOut = (msg) => {
      const data = JSON.stringify(msg)
      window.ReactNativeWebView?.postMessage(data)
      try { window.parent?.postMessage(data, '*') } catch {}
    }

    api.renderFinished.on(() => postOut({ type: 'ready' }))
    api.error.on((e) => postOut({ type: 'error', message: e.message }))
  </script>
</body>
</html>
```

```types/tabMessage.ts
export type TabInboundMessage =
  | { type: 'setScore';    gp5Base64: string }
  | { type: 'scrollToBar'; barIndex:  number }
  | { type: 'setTheme';    colors: Record<string, string> }

export type TabOutboundMessage =
  | { type: 'ready' }
  | { type: 'error'; message: string }

export const encodeTabMessage = (msg: TabInboundMessage): string => JSON.stringify(msg)

export const decodeTabMessage = (raw: string): TabOutboundMessage | null => {
  try { return JSON.parse(raw) as TabOutboundMessage }
  catch { return null }
}
```

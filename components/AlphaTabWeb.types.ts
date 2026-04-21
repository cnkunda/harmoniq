import type { StyleProp, ViewStyle } from 'react-native'

import type { SoundFontProfileId } from '@/src/audio/soundfontProfiles'
import type { TabRenderPresetName } from '@/src/session/tabThemePresets'
import type { NoteEventMessage, SongScoreMeta, TabThemeColors } from '@/types/tabMessage'

export type AlphaTabWebProps = {
  gp5Base64?: string | null
  /** Fetch URL for server prerender JSON — static SVG overlay until AlphaTab finishes layout (PRIORITIES §59). */
  prerenderArtifactUrl?: string | null
  audioSrc?: string | null
  transposeSemitones?: number
  /** Commit 60: AlphaTab synth bank (`general_user` | `fluid_r3_mono`). */
  soundFontProfile?: SoundFontProfileId
  /** Session step preset (Commit 56); default `study`. */
  renderPreset?: TabRenderPresetName
  /** Merged over README / harness defaults (`TAB_HARNESS_THEME`). */
  theme?: Partial<TabThemeColors>
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onError?: (message: string) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
  /** AlphaTab player seeked the score (e.g. bar click) — move stem/Web Audio transport to this time. */
  onScoreSeekMs?: (positionMs: number) => void
  /** Listening follow mode: disable score-originated seek/tap interactions. */
  readOnlyFollowMode?: boolean
  /** Static score metadata after load / render (web DOM path). */
  onSongDetails?: (score: SongScoreMeta) => void
  /** Live master bar + GP section label when playback position changes (web DOM path). */
  onSongPlayback?: (payload: { masterBarIndex: number; sectionLabel: string | null }) => void
  /** Commit 61: 5s windowed `runtimeDiagnostics` to `alphaTabRuntimeDiagStore` (dev / opt-in). */
  runtimeDiagnosticsEnabled?: boolean
}

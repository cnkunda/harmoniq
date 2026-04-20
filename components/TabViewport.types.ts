import type { StyleProp, ViewStyle } from 'react-native'
import type { SoundFontProfileId } from '@/src/audio/soundfontProfiles'
import type { TabRenderPresetName } from '@/src/session/tabThemePresets'
import type { NoteEventMessage, SongScoreMeta } from '@/types/tabMessage'

export type TabViewportProps = {
  gp5Base64?: string | null
  prerenderArtifactUrl?: string | null
  audioSrc?: string | null
  transposeSemitones?: number
  /** Commit 60: AlphaTab synth bank. */
  soundFontProfile?: SoundFontProfileId
  /** AlphaTab display preset for session step (Commit 56). */
  renderPreset?: TabRenderPresetName
  style?: StyleProp<ViewStyle>
  onReady?: () => void
  onError?: (message: string) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
  onScoreSeekMs?: (positionMs: number) => void
  onSongDetails?: (score: SongScoreMeta) => void
  onSongPlayback?: (payload: { masterBarIndex: number; sectionLabel: string | null }) => void
  /** Commit 61: enable harness + store runtime diagnostics. */
  runtimeDiagnosticsEnabled?: boolean
}

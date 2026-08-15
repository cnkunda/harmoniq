import type { StyleProp, ViewStyle } from 'react-native'
import type { SoundFontProfileId } from '@/src/audio/soundfontProfiles'
import type { TabRenderPresetName } from '@/src/session/tabThemePresets'
import type { NoteEventMessage, SongScoreMeta } from '@/types/tabMessage'
import type { LyricWord } from './LyricsStrip'

export type TabViewportProps = {
  gp5Base64?: string | null
  /** MusicXML is primary (Commit 107); GP5 falls back when absent. */
  musicXml?: string | null
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
  /** Listening follow mode: disable user score tap/seek interactions in AlphaTab host. */
  readOnlyFollowMode?: boolean
  onSongDetails?: (score: SongScoreMeta) => void
  onSongPlayback?: (payload: { masterBarIndex: number; sectionLabel: string | null }) => void
  runtimeDiagnosticsEnabled?: boolean
  lyricWords?: LyricWord[]
  playbackSec?: number
  songTitle?: string
  songArtist?: string
  tabVariant?: 'full' | 'skeleton' | 'alt'
  hasFull?: boolean
  hasSkeleton?: boolean
  hasAlt?: boolean
  onTabVariantChange?: (v: 'full' | 'skeleton' | 'alt') => void
  onSeekToStart?: () => void
}
